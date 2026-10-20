import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { GraphExplorer } from './GraphExplorer';
import { defaultProfile } from './contracts';
import type { Graph } from './contracts';

function makeGraph(generation = 'gen-1'): Graph {
  return {
    schema_version: 1,
    repo_id: 'repo-1',
    generation_id: generation,
    profile: defaultProfile,
    status: 'complete',
    sources: [{ id: 's1', path: 'src/a.cpp', sha256: 'hash', size: 100 }],
    nodes: [
      { id: 'n1', kind: 'function', name: 'decode_record', evidence_ids: ['e1'], properties: { translation_unit: 'src/a.cpp' } },
      { id: 'n2', kind: 'record', name: 'CustomerRecord', evidence_ids: ['e1'], properties: { translation_unit: 'src/a.cpp' } },
    ],
    edges: [
      { id: 'edge-1', source: 'n1', target: 'n2', kind: 'REFERENCES', evidence_ids: ['e1'] },
    ],
    evidence: [{ id: 'e1', source_id: 's1', start_byte: 0, end_byte: 50, line_start: 1, line_end: 5 }],
    diagnostics: [],
  };
}

describe('GraphExplorer zoom and pan viewport', () => {
  it('zooms in, zooms out, enforces scale limits, and recovers with Fit graph', async () => {
    const user = userEvent.setup();
    render(<GraphExplorer graph={makeGraph()} selected={null} onSelect={() => {}} />);

    const viewport = document.querySelector('svg g.graph-viewport')!;
    const zoomIn = screen.getByRole('button', { name: 'Zoom in' });
    const zoomOut = screen.getByRole('button', { name: 'Zoom out' });
    const fitGraph = screen.getByRole('button', { name: 'Fit graph' });

    expect(viewport).toHaveAttribute('transform', 'translate(0,0) scale(1)');
    expect(screen.getByLabelText('Graph zoom scale')).toHaveTextContent('Zoom: 100%');
    expect(fitGraph).toBeDisabled();

    await user.click(zoomIn);
    expect(screen.getByLabelText('Graph zoom scale')).toHaveTextContent('Zoom: 125%');
    expect(viewport.getAttribute('transform')).toContain('scale(1.25)');
    expect(fitGraph).toBeEnabled();

    for (let i = 0; i < 8; i++) {
      if (!zoomIn.hasAttribute('disabled')) await user.click(zoomIn);
    }
    expect(screen.getByLabelText('Graph zoom scale')).toHaveTextContent('Zoom: 300%');
    expect(zoomIn).toBeDisabled();
    expect(viewport.getAttribute('transform')).toContain('scale(3)');

    await user.click(fitGraph);
    expect(screen.getByLabelText('Graph zoom scale')).toHaveTextContent('Zoom: 100%');
    expect(viewport).toHaveAttribute('transform', 'translate(0,0) scale(1)');
    expect(fitGraph).toBeDisabled();

    for (let i = 0; i < 6; i++) {
      if (!zoomOut.hasAttribute('disabled')) await user.click(zoomOut);
    }
    expect(screen.getByLabelText('Graph zoom scale')).toHaveTextContent('Zoom: 50%');
    expect(zoomOut).toBeDisabled();
    expect(viewport.getAttribute('transform')).toContain('scale(0.5)');
  });

  it.each([
    [390, 120],
    [390, 360],
    [780, 120],
  ])('pans at uniform SVG scale in a %ix%i viewport without selecting a dragged node', (width, height) => {
    const onSelect = vi.fn();
    render(<GraphExplorer graph={makeGraph()} selected={null} onSelect={onSelect} />);

    const svg = screen.getByRole('group', { name: /Bounded structural graph/ });
    const viewport = document.querySelector('svg g.graph-viewport')!;
    const node = screen.getByRole('button', { name: 'Inspect function decode_record' });

    vi.spyOn(svg, 'getBoundingClientRect').mockReturnValue({
      width, height, top: 0, left: 0, right: width, bottom: height, x: 0, y: 0, toJSON: () => ({}),
    });

    fireEvent.pointerDown(node, { pointerId: 1, button: 0, clientX: 100, clientY: 50 });
    fireEvent.pointerMove(svg, { pointerId: 1, clientX: 130, clientY: 65 });
    fireEvent.pointerUp(svg, { pointerId: 1, clientX: 130, clientY: 65 });
    fireEvent.click(node);

    expect(viewport).toHaveAttribute('transform', 'translate(60,30) scale(1)');
    expect(onSelect).not.toHaveBeenCalled();

    // Subsequent clean click selects the node normally
    fireEvent.pointerDown(node, { pointerId: 2, button: 0, clientX: 100, clientY: 50 });
    fireEvent.pointerUp(node, { pointerId: 2, clientX: 100, clientY: 50 });
    fireEvent.click(node);
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'n1' }));
  });

  it.each(['pointerup', 'pointercancel'])('ends a pending gesture on %s outside the graph', event => {
    const onSelect = vi.fn();
    render(<GraphExplorer graph={makeGraph()} selected={null} onSelect={onSelect} />);
    const svg = screen.getByRole('group', { name: /Bounded structural graph/ });
    const viewport = document.querySelector('svg g.graph-viewport')!;
    const node = screen.getByRole('button', { name: 'Inspect function decode_record' });

    fireEvent.pointerDown(node, { pointerId: 3, button: 0, clientX: 100, clientY: 50 });
    fireEvent(window, new PointerEvent(event, { pointerId: 3 }));
    fireEvent.pointerMove(svg, { pointerId: 3, clientX: 200, clientY: 100 });
    expect(viewport).toHaveAttribute('transform', 'translate(0,0) scale(1)');
    expect(svg).not.toHaveClass('dragging');
    fireEvent.click(node);
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'n1' }));
  });

  it('cleans up drag state on pointercancel or window blur without blocking subsequent clicks', () => {
    const onSelect = vi.fn();
    render(<GraphExplorer graph={makeGraph()} selected={null} onSelect={onSelect} />);

    const svg = screen.getByRole('group', { name: /Bounded structural graph/ });
    const node = screen.getByRole('button', { name: 'Inspect function decode_record' });

    fireEvent.pointerDown(node, { pointerId: 7, button: 0, clientX: 40, clientY: 40 });
    fireEvent.pointerMove(svg, { pointerId: 7, clientX: 80, clientY: 80 });
    expect(svg).toHaveClass('dragging');

    fireEvent.pointerCancel(svg, { pointerId: 7 });
    expect(svg).not.toHaveClass('dragging');

    fireEvent.click(node);
    expect(onSelect).toHaveBeenCalledTimes(1);

    fireEvent.pointerDown(node, { pointerId: 8, button: 0, clientX: 40, clientY: 40 });
    fireEvent.pointerMove(svg, { pointerId: 8, clientX: 90, clientY: 90 });
    expect(svg).toHaveClass('dragging');
    fireEvent(window, new Event('blur'));
    expect(svg).not.toHaveClass('dragging');
  });

  it('supports keyboard zoom and pan on focused SVG canvas without hijacking node activation or search input', async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<GraphExplorer graph={makeGraph()} selected={null} onSelect={onSelect} />);

    const svg = screen.getByRole('group', { name: /Bounded structural graph/ });
    const viewport = document.querySelector('svg g.graph-viewport')!;
    const node = screen.getByRole('button', { name: 'Inspect record CustomerRecord' });

    svg.focus();
    fireEvent.keyDown(svg, { key: '+', ctrlKey: true });
    fireEvent.keyDown(svg, { key: '+', metaKey: true });
    expect(screen.getByLabelText('Graph zoom scale')).toHaveTextContent('Zoom: 100%');
    fireEvent.keyDown(svg, { key: '+' });
    expect(screen.getByLabelText('Graph zoom scale')).toHaveTextContent('Zoom: 125%');
    fireEvent.keyDown(svg, { key: 'ArrowRight' });
    expect(viewport.getAttribute('transform')).toBe('translate(-153.5,-30) scale(1.25)');

    // Pressing Enter/Space on a focused node selects the node and does not reset/alter canvas zoom
    node.focus();
    fireEvent.keyDown(node, { key: 'Enter' });
    expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: 'n2' }));
    expect(screen.getByLabelText('Graph zoom scale')).toHaveTextContent('Zoom: 125%');

    // Pressing '0' on canvas resets view
    svg.focus();
    fireEvent.keyDown(svg, { key: '0' });
    expect(viewport).toHaveAttribute('transform', 'translate(0,0) scale(1)');

    // Typing in search input works normally and resets view on filter change
    fireEvent.keyDown(svg, { key: '+' });
    expect(screen.getByLabelText('Graph zoom scale')).toHaveTextContent('Zoom: 125%');
    const search = screen.getByLabelText('Find symbol or identifier');
    await user.type(search, 'decode');
    expect(search).toHaveValue('decode');
    expect(screen.getByLabelText('Graph zoom scale')).toHaveTextContent('Zoom: 100%');
    expect(document.querySelector('svg g.graph-viewport')).toHaveAttribute('transform', 'translate(0,0) scale(1)');
  });

  it('resets the viewport transform when the graph generation changes', () => {
    const { rerender } = render(<GraphExplorer graph={makeGraph('gen-1')} selected={null} onSelect={() => {}} />);
    const svg = screen.getByRole('group', { name: /Bounded structural graph/ });
    fireEvent.keyDown(svg, { key: '+' });
    expect(screen.getByLabelText('Graph zoom scale')).toHaveTextContent('Zoom: 125%');

    rerender(<GraphExplorer graph={makeGraph('gen-2')} selected={null} onSelect={() => {}} />);
    expect(screen.getByLabelText('Graph zoom scale')).toHaveTextContent('Zoom: 100%');
    expect(document.querySelector('svg g.graph-viewport')).toHaveAttribute('transform', 'translate(0,0) scale(1)');
  });
});
