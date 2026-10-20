from __future__ import annotations

import hashlib
import hmac
import io
import json
import logging
import secrets
import threading
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict

from .core import Profile, WorkbenchError
from .conversion import ConversionRequest, ConversionResult
from .job_store import ConversionRecord, JobStore, SESSION_SECONDS, owner_hash
from .service import WorkbenchService, default_state_dir

LOGGER = logging.getLogger(__name__)
TERMINAL_STATES = {"succeeded", "partial", "failed", "cancelled", "blocked", "interrupted"}
SAFE_HOSTS = {"127.0.0.1", "localhost", "::1"}


@dataclass
class Job:
    id: str
    repo_id: str
    owner: str
    status: str = "queued"
    stage: str = "queued"
    error: dict[str, str] | None = None
    kind: str = "graph"
    completed_files: int = 0
    total_files: int = 0
    result: ConversionResult | None = None
    request: ConversionRequest | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    cancelled: threading.Event = field(default_factory=threading.Event)

    def public(self) -> dict:
        return {
            "id": self.id,
            "repo_id": self.repo_id,
            "status": self.status,
            "stage": self.stage,
            "error": self.error,
            "kind": self.kind,
            "completed_files": self.completed_files,
            "total_files": self.total_files,
            "conversion": self.result.public() if self.result else None,
            "request": self.request.model_dump() if self.request else None,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_record(cls, record: ConversionRecord) -> Job:
        return cls(
            id=record.id, repo_id=record.repo_id, owner=record.owner_hash, status=record.status,
            stage=record.stage, error=record.error, kind="conversion",
            completed_files=record.completed_files, total_files=record.total_files,
            result=record.result, request=record.request,
            created_at=record.created_at, updated_at=record.updated_at,
        )


class JobManager:
    def __init__(self, service: WorkbenchService) -> None:
        self.service = service
        self.jobs: dict[str, Job] = {}
        self.lock = threading.RLock()
        self.store = JobStore(service.registry.directory)
        self.store.acquire_runtime()
        try:
            self.store.recover()
        except WorkbenchError:
            self.store.release_runtime()
            raise
        self.worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="graph")

    def _save(self, job: Job) -> None:
        job.updated_at = time.time()
        if job.request is not None:
            self.store.save(ConversionRecord(
                id=job.id, repo_id=job.repo_id, owner_hash=job.owner, status=job.status,
                stage=job.stage, error=job.error, completed_files=job.completed_files,
                total_files=job.total_files, request=job.request, result=job.result,
                created_at=job.created_at, updated_at=job.updated_at,
            ))

    def _save_failure(self, job: Job) -> None:
        try:
            self._save(job)
        except WorkbenchError as exc:
            LOGGER.error("Cannot persist job failure (%s)", exc.code)
            job.status = "failed"
            job.result = None
            job.error = {"code": exc.code, "message": str(exc)}

    def submit(self, repo_id: str, profile: Profile, owner: str, *,
               conversion: ConversionRequest | None = None) -> dict:
        with self.lock:
            self.service.registry.get(repo_id)
            if any(job.status not in TERMINAL_STATES for job in self.jobs.values()):
                raise WorkbenchError("busy", "Another generation or conversion is active. Wait or cancel it first.")
            if conversion and sum(job.kind == "conversion" for job in self.jobs.values()) >= 8:
                oldest = next(key for key, job in self.jobs.items()
                              if job.kind == "conversion" and job.status in TERMINAL_STATES)
                del self.jobs[oldest]
            if len(self.jobs) >= 100:
                oldest = next(
                    (key for key, job in self.jobs.items() if job.status in TERMINAL_STATES), None
                )
                if oldest:
                    del self.jobs[oldest]
            job = Job(secrets.token_hex(16), repo_id, owner_hash(owner))
            if conversion:
                job.kind = "conversion"
                job.total_files = len(conversion.paths)
                job.request = conversion
            self._save(job)
            self.jobs[job.id] = job
            self.worker.submit(self._run, job, profile, conversion)
            return job.public()

    def _run(self, job: Job, profile: Profile, conversion: ConversionRequest | None) -> None:
        def stage(value: str, completed: int = 0, total: int = 0) -> None:
            with self.lock:
                if job.cancelled.is_set():
                    raise WorkbenchError("cancelled", "The job was cancelled.")
                job.stage = value
                job.completed_files = completed
                job.total_files = total
                self._save(job)

        try:
            with self.lock:
                job.status = "running"
                job.stage = "extracting"
                self._save(job)
            if conversion:
                result = self.service.convert(
                    job.repo_id, conversion, cancelled=job.cancelled.is_set, on_progress=stage,
                )
                with self.lock:
                    if job.cancelled.is_set():
                        raise WorkbenchError("cancelled", "Conversion was cancelled.")
                    job.result = result
                    job.status = "blocked" if result.blocked else "succeeded"
                    job.stage = "finished"
                    self._save(job)
                return
            graph = self.service.generate(
                job.repo_id, profile, cancelled=job.cancelled.is_set, on_stage=stage
            )
            with self.lock:
                job.status = "partial" if graph.status == "partial" else "succeeded"
                job.stage = "finished"
        except WorkbenchError as exc:
            with self.lock:
                job.status = "cancelled" if exc.code == "cancelled" else "failed"
                job.result = None
                job.stage = "finished"
                job.error = {"code": exc.code, "message": str(exc)}
                self._save_failure(job)
        except Exception as exc:
            # Background failures have no request handler; log only the exception class.
            LOGGER.error("Job failed (%s)", type(exc).__name__)
            with self.lock:
                job.status = "failed"
                job.result = None
                job.stage = "finished"
                job.error = {
                    "code": "internal_error",
                    "message": "The job failed unexpectedly. Check the local diagnostic log.",
                }
                self._save_failure(job)

    def _owned(self, job_id: str, owner: str) -> Job:
        job = self.jobs.get(job_id)
        if job is None:
            return Job.from_record(self.store.get(job_id, owner_hash(owner)))
        if not secrets.compare_digest(job.owner, owner_hash(owner)):
            raise WorkbenchError("not_found", "Job was not found in this browser session.")
        return job

    def get(self, job_id: str, owner: str) -> dict:
        with self.lock:
            return self._owned(job_id, owner).public()

    def cancel(self, job_id: str, owner: str) -> dict:
        with self.lock:
            job = self._owned(job_id, owner)
            if job.stage == "publishing" and job.status not in TERMINAL_STATES:
                raise WorkbenchError("busy", "Publication has started and cannot be cancelled.")
            if job.status not in TERMINAL_STATES:
                job.cancelled.set()
                job.stage = "cancelling"
                self._save(job)
            return job.public()

    def active(self, repo_id: str) -> bool:
        with self.lock:
            return any(
                job.repo_id == repo_id and job.status not in TERMINAL_STATES
                for job in self.jobs.values()
            )

    def conversion(self, job_id: str, owner: str) -> tuple[str, ConversionResult]:
        with self.lock:
            job = self._owned(job_id, owner)
            if job.kind != "conversion":
                raise WorkbenchError("not_found", "Conversion job was not found.")
            if job.result is None:
                raise WorkbenchError("busy", "Conversion results are not available for this job.")
            return job.repo_id, job.result

    def forget(self, repo_id: str) -> None:
        with self.lock:
            self.store.forget(repo_id)
            self.jobs = {key: job for key, job in self.jobs.items() if job.repo_id != repo_id}

    def remove(self, repo_id: str) -> None:
        with self.lock:
            if self.active(repo_id):
                raise WorkbenchError("busy", "Cancel generation or conversion before removing this repository.")
            self.service.delete(repo_id)
            self.forget(repo_id)

    def history(self, repo_id: str, owner: str) -> list[dict]:
        with self.lock:
            self.service.registry.get(repo_id)
            return [Job.from_record(record).public() for record in self.store.list(repo_id, owner_hash(owner))]

    def close(self) -> None:
        with self.lock:
            for job in self.jobs.values():
                if job.stage != "publishing":
                    job.cancelled.set()
        self.worker.shutdown(wait=True, cancel_futures=True)
        with self.lock:
            for job in self.jobs.values():
                if job.status not in TERMINAL_STATES:
                    job.status = "interrupted"
                    job.stage = "finished"
                    job.error = {"code": "job_interrupted", "message": "Server stopped. Start a new job."}
                    self._save_failure(job)
        self.store.release_runtime()


class ExportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["as-built", "spec-draft"]


def error_response(code: str, message: str, status: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status)


def create_app(service: WorkbenchService | None = None) -> FastAPI:
    service = service or WorkbenchService(default_state_dir())
    jobs = JobManager(service)
    signing_key = secrets.token_bytes(32)
    web_root = Path(__file__).resolve().parents[2] / "web" / "dist"

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        yield
        jobs.close()

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.jobs = jobs

    def csrf(session: str) -> str:
        return hmac.new(signing_key, session.encode(), hashlib.sha256).hexdigest()

    @app.middleware("http")
    async def local_boundary(request: Request, call_next):
        try:
            host = request.url.hostname
        except ValueError:
            return error_response("forbidden_host", "Invalid loopback host.", 403)
        if host not in SAFE_HOSTS:
            return error_response("forbidden_host", "Only loopback hosts are allowed.", 403)
        origin = request.headers.get("origin")
        if origin is not None and origin != f"{request.url.scheme}://{request.headers.get('host')}":
            return error_response("forbidden_origin", "Cross-origin requests are not allowed.", 403)
        if request.headers.get("sec-fetch-site") == "cross-site":
            return error_response("forbidden_origin", "Cross-site requests are not allowed.", 403)
        length = request.headers.get("content-length")
        if length:
            try:
                if int(length) < 0 or int(length) > 16_384:
                    return error_response("budget_exceeded", "Request exceeds the size limit.", 413)
            except ValueError:
                return error_response("invalid_request", "Invalid content length.", 400)
        # Bound streamed/chunked bodies as well as declared content lengths.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 16_384:
                return error_response("budget_exceeded", "Request exceeds the size limit.", 413)
        request._body = bytes(body)
        if request.url.path.startswith("/api/") and request.url.path != "/api/session":
            session = request.cookies.get("workbench_session", "")
            try:
                valid = jobs.store.valid_session(session)
            except WorkbenchError as exc:
                return error_response(exc.code, str(exc), 503)
            if not valid:
                return error_response("session_required", "Refresh to establish a local session.", 401)
            request.state.owner = session
            if request.method not in {"GET", "HEAD", "OPTIONS"}:
                token = request.headers.get("x-csrf-token", "")
                if not secrets.compare_digest(token, csrf(session)):
                    return error_response("csrf_required", "Refresh the local session and retry.", 403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "connect-src 'self'; img-src 'self' data:; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'"
        )
        return response

    @app.exception_handler(WorkbenchError)
    async def workbench_error(_request: Request, exc: WorkbenchError):
        status = {
            "not_found": 404,
            "forbidden_path": 403,
            "source_changed": 409,
            "stale_evidence": 409,
            "busy": 409,
            "backend_unavailable": 503,
            "database_unavailable": 503,
            "credentials_required": 503,
            "job_store_unavailable": 503,
            "job_store_invalid": 503,
            "session_limit": 429,
            "graph_required": 409,
            "graph_changed": 409,
            "graph_profile_mismatch": 409,
            "incomplete_graph": 409,
            "conversion_outdated": 409,
            "budget_exceeded": 413,
        }.get(exc.code, 422)
        return error_response(exc.code, str(exc), status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, _exc: RequestValidationError):
        return error_response("invalid_request", "Request does not match the supported schema.", 422)

    @app.exception_handler(Exception)
    async def unexpected_error(_request: Request, exc: Exception):
        LOGGER.error("Request failed (%s)", type(exc).__name__)
        return error_response("internal_error", "An unexpected local service error occurred.", 500)

    @app.get("/api/session")
    def session(request: Request):
        token = jobs.store.session(request.cookies.get("workbench_session", ""))
        response = JSONResponse({"csrf_token": csrf(token)})
        response.set_cookie(
            "workbench_session", token, httponly=True, samesite="strict", path="/api",
            max_age=SESSION_SECONDS,
        )
        return response

    @app.get("/api/health")
    def health():
        return service.check_connection()

    @app.get("/api/health/sqlite")
    def sqlite_health():
        return jobs.store.check_connection()

    @app.get("/api/repos")
    def repositories():
        return {"repos": service.list_repos()}

    @app.post("/api/repos/{repo_id}/assessment")
    def assess(repo_id: str, profile: Profile):
        return service.assess(repo_id, profile)

    @app.post("/api/repos/{repo_id}/generations", status_code=202)
    def generate(repo_id: str, profile: Profile, request: Request):
        return jobs.submit(repo_id, profile, request.state.owner)

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str, request: Request):
        return jobs.get(job_id, request.state.owner)

    @app.post("/api/jobs/{job_id}/cancel")
    def cancel_job(job_id: str, request: Request):
        return jobs.cancel(job_id, request.state.owner)

    @app.post("/api/repos/{repo_id}/conversions", status_code=202)
    def start_conversion(repo_id: str, payload: ConversionRequest, request: Request):
        return jobs.submit(repo_id, payload.profile, request.state.owner, conversion=payload)

    @app.get("/api/repos/{repo_id}/conversions")
    def conversion_history(repo_id: str, request: Request):
        return {"jobs": jobs.history(repo_id, request.state.owner)}

    @app.get("/api/conversions/{job_id}/preview")
    def conversion_preview(job_id: str, path: str, request: Request):
        repo_id, result = jobs.conversion(job_id, request.state.owner)
        service.verify_conversion(repo_id, result)
        repository = service.registry.get(repo_id)
        preview = result.preview(repository.root, path)
        service.verify_conversion(repo_id, result)
        return preview

    @app.get("/api/conversions/{job_id}/download")
    def conversion_download(job_id: str, request: Request):
        repo_id, result = jobs.conversion(job_id, request.state.owner)
        service.verify_conversion(repo_id, result)
        repository = service.registry.get(repo_id)
        files = result.output_files(repository.root)
        manifest = {
            "schema_version": 1, "repo_id": repo_id, **result.public(),
            "request": jobs.get(job_id, request.state.owner)["request"],
            "sources": [source.model_dump() for source in result.sources],
            "outputs": {name: hashlib.sha256(content.encode("utf-8")).hexdigest()
                        for name, content in files.items()},
            "notice": "Unreviewed migration draft. Headers are included unchanged. "
                      "No IBM API, EBCDIC or packed-decimal conversion is provided. "
                      "Original runtime bounds and business logic still require review. "
                      "Downloaded copies cannot be recalled.",
        }
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                archive.writestr(name, content)
            archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        result.verify(repository.root)
        service.verify_conversion(repo_id, result)
        return Response(output.getvalue(), media_type="application/zip",
                        headers={"Content-Disposition": 'attachment; filename="x86-conversion-draft.zip"'})

    @app.get("/api/repos/{repo_id}/graph")
    def graph(repo_id: str):
        return service.load_graph(repo_id)

    @app.get("/api/repos/{repo_id}/evidence/{evidence_id}")
    def evidence(repo_id: str, evidence_id: str):
        return service.evidence(repo_id, evidence_id)

    @app.post("/api/repos/{repo_id}/exports")
    def preview(repo_id: str, payload: ExportRequest):
        current = service.load_graph(repo_id)
        from .documents import render_documents

        documents = render_documents(current, payload.kind)
        service.verify_graph(repo_id, current)
        return {
            "id": f"{current.generation_id}-{payload.kind}",
            "kind": payload.kind,
            "generation_id": current.generation_id,
            "files": [{"name": name, "content": content} for name, content in documents.items()],
        }

    @app.get("/api/repos/{repo_id}/export")
    def download(repo_id: str, kind: Literal["as-built", "spec-draft"]):
        from .documents import render_documents

        current = service.load_graph(repo_id)
        documents = render_documents(current, kind)
        manifest = {
            "schema_version": 1,
            "repo_id": repo_id,
            "generation_id": current.generation_id,
            "kind": kind,
            "sources": [source.model_dump() for source in current.sources],
            "files": {
                name: hashlib.sha256(content.encode("utf-8")).hexdigest()
                for name, content in documents.items()
            },
            "notice": "Explicit export. Copied downloads cannot be recalled; recheck source hashes before reuse.",
        }
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in documents.items():
                if Path(name).name != name:
                    raise WorkbenchError("invalid_export", "Document export contains an unsafe name.")
                archive.writestr(name, content)
            archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True))
        service.verify_graph(repo_id, current)
        return Response(
            output.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="workbench-{kind}.zip"'},
        )

    @app.delete("/api/repos/{repo_id}", status_code=204)
    def remove(repo_id: str):
        jobs.remove(repo_id)
        return Response(status_code=204)

    @app.get("/")
    def index():
        path = web_root / "index.html"
        if not path.is_file():
            return error_response(
                "ui_not_built", "Build the web interface with npm run build in web/.", 503
            )
        return FileResponse(path)

    @app.get("/assets/{asset_path:path}")
    def asset(asset_path: str):
        root = (web_root / "assets").resolve()
        target = (root / asset_path).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            return error_response("not_found", "Asset was not found.", 404)
        return FileResponse(target)

    return app
