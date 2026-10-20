import { useEffect, useMemo, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from 'react';
import type { Graph, GraphNode } from './contracts';

const SVG_LIMIT = 36;
const PAGE_SIZE = 100;
const EDGE_LIMIT = 100;
const BASE_WIDTH = 780;
const MIN_SCALE = 0.5;
const MAX_SCALE = 3;
const ZOOM_STEP = 1.25;
const PAN_STEP = 56;
const DRAG_THRESHOLD_PX = 4;

interface ViewState {
  scale: number;
  x: number;
  y: number;
}

const INITIAL_VIEW: ViewState = { scale: 1, x: 0, y: 0 };

function clampScale(scale: number): number {
  if (!Number.isFinite(scale)) return 1;
  return Math.min(MAX_SCALE, Math.max(MIN_SCALE, Math.round(scale * 1000) / 1000));
}

function clampOffset(value: number, limit: number): number {
  if (!Number.isFinite(value)) return 0;
  return Math.min(limit, Math.max(-limit, Math.round(value * 100) / 100));
}

function normalizeView(next: ViewState, baseHeight: number): ViewState {
  const scale = clampScale(next.scale);
  const maxX = Math.max(BASE_WIDTH, BASE_WIDTH * scale);
  const maxY = Math.max(baseHeight, baseHeight * scale);
  return {
    scale,
    x: clampOffset(next.x, maxX),
    y: clampOffset(next.y, maxY),
  };
}

function zoomAroundPoint(current: ViewState, nextScale: number, anchorX: number, anchorY: number, baseHeight: number): ViewState {
  const scale = clampScale(nextScale);
  if (scale === current.scale) return current;
  const worldX = (anchorX - current.x) / current.scale;
  const worldY = (anchorY - current.y) / current.scale;
  return normalizeView({
    scale,
    x: anchorX - worldX * scale,
    y: anchorY - worldY * scale,
  }, baseHeight);
}

function contextValues(node: GraphNode): string[] {
  return ['target', 'target_id', 'translation_unit', 'translation_unit_id', 'tu', 'tu_id', 'config']
    .flatMap(key => {
      const value = node.properties[key];
      return typeof value === 'string' ? [`${key}: ${value}`] : [];
    });
}

export function GraphExplorer({ graph, selected, onSelect }: {
  graph: Graph; selected: GraphNode | null; onSelect: (node: GraphNode) => void;
}) {
  const [query, setQuery] = useState('');
  const [kind, setKind] = useState('');
  const [context, setContext] = useState('');
  const [relation, setRelation] = useState('');
  const [page, setPage] = useState(0);
  const [view, setView] = useState<ViewState>(INITIAL_VIEW);
  const [isDragging, setIsDragging] = useState(false);
  const svgRef = useRef<SVGSVGElement | null>(null);
  const dragSession = useRef<{
    pointerId: number;
    startClientX: number;
    startClientY: number;
    originX: number;
    originY: number;
    moved: boolean;
    captured: boolean;
  } | null>(null);
  const suppressClick = useRef(false);

  const index = useMemo(() => {
    const contexts = new Map(graph.nodes.map(node => [node.id, contextValues(node)]));
    const adjacent = new Map<string, typeof graph.edges>();
    for (const edge of graph.edges) {
      for (const id of [edge.source, edge.target]) {
        const list = adjacent.get(id) ?? [];
        list.push(edge);
        adjacent.set(id, list);
      }
    }
    return {
      contexts, adjacent,
      kinds: [...new Set(graph.nodes.map(node => node.kind))].sort(),
      relations: [...new Set(graph.edges.map(edge => edge.kind))].sort(),
      scopes: [...new Set([...contexts.values()].flat())].sort(),
    };
  }, [graph]);
  const filtered = useMemo(() => {
    const term = query.trim().toLowerCase();
    return graph.nodes.filter(node =>
      (!term || `${node.name} ${node.id}`.toLowerCase().includes(term)) &&
      (!kind || node.kind === kind) &&
      (!context || index.contexts.get(node.id)?.includes(context)) &&
      (!relation || index.adjacent.get(node.id)?.some(edge => edge.kind === relation)));
  }, [graph, query, kind, context, relation, index]);
  const visible = filtered.slice(0, SVG_LIMIT);
  const baseHeight = Math.max(240, Math.ceil(visible.length / 3) * 62 + 24);
  const positions = new Map(visible.map((node, i) => [node.id, {
    x: 15 + (i % 3) * 255, y: 18 + Math.floor(i / 3) * 62,
  }]));
  const visibleEdges = graph.edges.filter(edge => positions.has(edge.source) &&
    positions.has(edge.target) && (!relation || edge.kind === relation)).slice(0, EDGE_LIMIT);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount - 1);
  const rows = filtered.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);

  const endDrag = (releaseCapture = true) => {
    const active = dragSession.current;
    if (!active) return;
    if (releaseCapture && active.captured && svgRef.current?.hasPointerCapture?.(active.pointerId)) {
      svgRef.current.releasePointerCapture(active.pointerId);
    }
    dragSession.current = null;
    setIsDragging(false);
  };

  const resetView = () => {
    endDrag();
    suppressClick.current = false;
    setView(INITIAL_VIEW);
  };

  useEffect(() => {
    endDrag();
    suppressClick.current = false;
    setView(INITIAL_VIEW);
  }, [graph.generation_id]);

  useEffect(() => {
    const onPointerUp = (event: PointerEvent) => {
      if (dragSession.current?.pointerId === event.pointerId) endDrag();
    };
    const onPointerCancel = (event: PointerEvent) => {
      if (dragSession.current?.pointerId !== event.pointerId) return;
      suppressClick.current = false;
      endDrag();
    };
    const onWindowBlur = () => {
      endDrag();
      suppressClick.current = false;
    };
    window.addEventListener('pointerup', onPointerUp);
    window.addEventListener('pointercancel', onPointerCancel);
    window.addEventListener('blur', onWindowBlur);
    return () => {
      window.removeEventListener('pointerup', onPointerUp);
      window.removeEventListener('pointercancel', onPointerCancel);
      window.removeEventListener('blur', onWindowBlur);
      endDrag();
    };
  }, []);

  const choose = (setter: (value: string) => void, value: string) => {
    setter(value);
    setPage(0);
    resetView();
  };

  const stepZoom = (factor: number) => {
    setView(current => zoomAroundPoint(current, current.scale * factor, BASE_WIDTH / 2, baseHeight / 2, baseHeight));
  };

  const stepPan = (dx: number, dy: number) => {
    setView(current => normalizeView({ scale: current.scale, x: current.x + dx, y: current.y + dy }, baseHeight));
  };

  const svgRatio = () => {
    const rect = svgRef.current?.getBoundingClientRect();
    const width = rect && rect.width > 0 ? rect.width : BASE_WIDTH;
    const height = rect && rect.height > 0 ? rect.height : baseHeight;
    return Math.max(BASE_WIDTH / width, baseHeight / height);
  };

  const handlePointerDown = (e: ReactPointerEvent<SVGSVGElement>) => {
    if (e.button !== 0 || dragSession.current) return;
    suppressClick.current = false;
    dragSession.current = {
      pointerId: e.pointerId,
      startClientX: e.clientX,
      startClientY: e.clientY,
      originX: view.x,
      originY: view.y,
      moved: false,
      captured: false,
    };
  };

  const handlePointerMove = (e: ReactPointerEvent<SVGSVGElement>) => {
    const active = dragSession.current;
    if (!active || active.pointerId !== e.pointerId) return;
    const deltaX = e.clientX - active.startClientX;
    const deltaY = e.clientY - active.startClientY;
    if (!active.moved && Math.hypot(deltaX, deltaY) >= DRAG_THRESHOLD_PX) {
      active.moved = true;
      suppressClick.current = true;
      setIsDragging(true);
      if (svgRef.current?.setPointerCapture) {
        svgRef.current.setPointerCapture(e.pointerId);
        active.captured = true;
      }
    }
    if (!active.moved) return;
    const ratio = svgRatio();
    setView(current => normalizeView({
      scale: current.scale,
      x: active.originX + deltaX * ratio,
      y: active.originY + deltaY * ratio,
    }, baseHeight));
  };

  const handlePointerUp = (e: ReactPointerEvent<SVGSVGElement>) => {
    const active = dragSession.current;
    if (!active || active.pointerId !== e.pointerId) return;
    endDrag();
  };

  const handlePointerCancel = (e: ReactPointerEvent<SVGSVGElement>) => {
    const active = dragSession.current;
    if (!active || active.pointerId !== e.pointerId) return;
    suppressClick.current = false;
    endDrag();
  };

  const handleCanvasKeyDown = (e: ReactKeyboardEvent<SVGSVGElement>) => {
    if (e.target !== e.currentTarget || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === '+' || e.key === '=') {
      e.preventDefault();
      stepZoom(ZOOM_STEP);
    } else if (e.key === '-' || e.key === '_') {
      e.preventDefault();
      stepZoom(1 / ZOOM_STEP);
    } else if (e.key === '0') {
      e.preventDefault();
      resetView();
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      stepPan(PAN_STEP, 0);
    } else if (e.key === 'ArrowRight') {
      e.preventDefault();
      stepPan(-PAN_STEP, 0);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      stepPan(0, PAN_STEP);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      stepPan(0, -PAN_STEP);
    }
  };

  const zoomPercent = `${Math.round(view.scale * 100)}%`;
  const isDefaultView = view.scale === 1 && view.x === 0 && view.y === 0;

  return <section className="panel graph-panel" aria-labelledby="graph-title">
    <div className="panel-heading"><h2 id="graph-title">Structural graph</h2>
      <span className="count">{filtered.length} / {graph.nodes.length} nodes</span></div>
    <div className="filters">
      <label className="search">Find symbol or identifier
        <input type="search" value={query} onChange={e => choose(setQuery, e.target.value)} placeholder="Search this generation" />
      </label>
      <label>Symbol kind<select value={kind} onChange={e => choose(setKind, e.target.value)}>
        <option value="">All kinds</option>{index.kinds.map(k => <option key={k}>{k}</option>)}
      </select></label>
      <label>Target / translation unit<select value={context} onChange={e => choose(setContext, e.target.value)}>
        <option value="">All contexts</option>{index.scopes.map(scope => <option key={scope}>{scope}</option>)}
      </select></label>
      <label>Relation<select value={relation} onChange={e => choose(setRelation, e.target.value)}>
        <option value="">All relations</option>{index.relations.map(k => <option key={k}>{k}</option>)}
      </select></label>
    </div>
    <p className="caption">Bounded index view · first {SVG_LIMIT} matching nodes / at most {EDGE_LIMIT} links.
      Lines represent recorded relations, not inferred calls. Use the table for full identifiers.</p>
    {filtered.length === 0 ? <p className="empty">No nodes match these filters. Clear a filter or inspect completeness diagnostics.</p> :
      <>
        <div className="graph-toolbar" role="toolbar" aria-label="Graph viewport controls">
          <div className="graph-controls">
            <button type="button" onClick={() => stepZoom(ZOOM_STEP)} disabled={view.scale >= MAX_SCALE}>Zoom in</button>
            <button type="button" onClick={() => stepZoom(1 / ZOOM_STEP)} disabled={view.scale <= MIN_SCALE}>Zoom out</button>
            <button type="button" onClick={resetView} disabled={isDefaultView}>Fit graph</button>
          </div>
          <span className="mono graph-scale" aria-live="polite" aria-label="Graph zoom scale">Zoom: {zoomPercent}</span>
          <span className="caption graph-hint">Drag to pan · focus canvas for +/-/0 and arrow keys</span>
        </div>
        <div className="graph-scroll">
          <svg ref={svgRef} className={`graph ${isDragging ? 'dragging' : ''}`}
            viewBox={`0 0 ${BASE_WIDTH} ${baseHeight}`}
            preserveAspectRatio="xMidYMid meet"
            tabIndex={0} role="group"
            aria-label="Bounded structural graph; equivalent node table below"
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerCancel={handlePointerCancel}
            onLostPointerCapture={() => endDrag(false)}
            onKeyDown={handleCanvasKeyDown}>
            <g className="graph-viewport" transform={`translate(${view.x},${view.y}) scale(${view.scale})`}>
              {visibleEdges.map(edge => {
                const a = positions.get(edge.source)!;
                const b = positions.get(edge.target)!;
                return <path key={edge.id} d={`M${a.x + 112},${a.y + 20} L${b.x + 112},${b.y + 20}`} className="graph-edge">
                  <title>{edge.kind}</title>
                </path>;
              })}
              {visible.map(node => {
                const position = positions.get(node.id)!;
                return <g key={node.id} transform={`translate(${position.x},${position.y})`}
                  className={`graph-node ${selected?.id === node.id ? 'selected' : ''}`} role="button" tabIndex={0}
                  aria-label={`Inspect ${node.kind} ${node.name}`} aria-pressed={selected?.id === node.id}
                  onClick={() => {
                    if (suppressClick.current) {
                      suppressClick.current = false;
                      return;
                    }
                    onSelect(node);
                  }}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); e.stopPropagation(); onSelect(node); } }}>
                  <title>{node.name} · {node.id}</title>
                  <rect width="232" height="43" rx="4" />
                  <text x="10" y="15" className="node-kind">{node.kind.slice(0, 29)}</text>
                  <text x="10" y="32">{node.name.length > 29 ? `${node.name.slice(0, 28)}…` : node.name}</text>
                </g>;
              })}
            </g>
          </svg>
        </div>
      </>}
    <div className="table-scroll"><table>
      <caption>Symbols — page {currentPage + 1} of {pageCount}, up to {PAGE_SIZE} rows per page</caption>
      <thead><tr><th scope="col">Symbol / identity</th><th scope="col">Kind</th><th scope="col">Context</th></tr></thead>
      <tbody>{rows.map(node => <tr key={node.id} className={selected?.id === node.id ? 'selected' : ''}>
        <td><button className="text-button symbol" onClick={() => onSelect(node)} aria-pressed={selected?.id === node.id}>{node.name}</button>
          <small className="mono identifier">{node.id}</small></td>
        <td>{node.kind}</td><td className="mono">{index.contexts.get(node.id)?.join(' · ') || 'Not recorded'}</td>
      </tr>)}</tbody>
    </table></div>
    <div className="pagination">
      <button disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous symbols</button>
      <button disabled={currentPage + 1 >= pageCount} onClick={() => setPage(currentPage + 1)}>Next symbols</button>
    </div>
  </section>;
}
