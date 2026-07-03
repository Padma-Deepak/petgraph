import { useRef, useCallback, useEffect, useState, useMemo } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import type { GraphNode, GraphLink, GraphData } from '../types';

// ── Colour palette ─────────────────────────────────────────────────────────
const PALETTE: Record<string, string> = {
  pet:       '#f59e0b',  // amber
  owner:     '#38bdf8',  // sky
  provider:  '#a78bfa',  // violet
  visit:     '#34d399',  // emerald
  symptom:   '#f43f5e',  // rose
  diagnosis: '#fb923c',  // orange
  medication:'#4ade80',  // green
  vaccine:   '#22d3ee',  // cyan
};

const TYPE_ICON: Record<string, string> = {
  pet: '🐾', owner: '👤', provider: '🏥', visit: '📋',
  symptom: '⚡', diagnosis: '🔬', medication: '💊', vaccine: '💉',
};

const BASE_R: Record<string, number> = {
  pet: 16, owner: 10, provider: 13, visit: 9,
  symptom: 10, diagnosis: 11, medication: 11, vaccine: 10,
};

// Ring order for initial layout (inner → outer)
const RING_ORDER = ['pet', 'owner', 'provider', 'visit', 'diagnosis', 'symptom', 'medication', 'vaccine'];

// ── Assign positions before first render ───────────────────────────────────
function applyRingLayout(nodes: GraphNode[]) {
  const byType: Record<string, GraphNode[]> = {};
  for (const n of nodes) (byType[n.type] = byType[n.type] || []).push(n);

  let ring = 0;
  for (const type of RING_ORDER) {
    const group = byType[type] || [];
    if (!group.length) continue;
    const radius = 90 + ring * 110;
    group.forEach((n, i) => {
      n.x = radius * Math.cos((2 * Math.PI * i) / group.length - Math.PI / 2);
      n.y = radius * Math.sin((2 * Math.PI * i) / group.length - Math.PI / 2);
    });
    ring++;
  }
}

interface Props {
  data: GraphData;
  traversalPath?: string[];
  anchorNodes?: string[];
  animating?: boolean;
  onNodeClick?: (node: GraphNode) => void;
}

export default function GraphCanvas({
  data,
  traversalPath = [],
  anchorNodes = [],
  animating = false,
  onNodeClick,
}: Props) {
  const fgRef = useRef<any>(null);
  const [visitedSet, setVisitedSet] = useState<Set<string>>(new Set());
  const [animStep, setAnimStep] = useState(0);
  const [hint, setHint] = useState(true);

  // Apply ring layout once when nodes change
  const layoutData = useMemo(() => {
    const nodes = data.nodes.map((n) => ({ ...n }));
    applyRingLayout(nodes);
    return { nodes, links: data.links };
  }, [data.nodes.length, data.links.length]); // eslint-disable-line

  // Traversal animation
  useEffect(() => {
    if (!animating || traversalPath.length === 0) {
      setVisitedSet(new Set());
      setAnimStep(0);
      return;
    }
    setVisitedSet(new Set());
    let step = 0;
    const id = setInterval(() => {
      step += 1;
      setAnimStep(step);
      setVisitedSet(new Set(traversalPath.slice(0, step)));
      if (step >= traversalPath.length) clearInterval(id);
    }, 180);
    return () => clearInterval(id);
  }, [animating, traversalPath]);

  // Configure d3 forces after mount for better spacing
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    fg.d3Force('charge').strength(-400);
    fg.d3Force('link').distance(120).strength(0.4);
    fg.d3Force('center').strength(0.05);
    fg.d3ReheatSimulation();
  }, [layoutData]);

  // Hide drag hint after 6 s
  useEffect(() => {
    const t = setTimeout(() => setHint(false), 6000);
    return () => clearTimeout(t);
  }, []);

  // Pin node after user drags it (so it stays where placed)
  const handleNodeDragEnd = useCallback((node: GraphNode) => {
    node.fx = node.x;
    node.fy = node.y;
  }, []);

  const handleNodeDrag = useCallback((node: GraphNode) => {
    node.fx = node.x;
    node.fy = node.y;
  }, []);

  // Double-click to unpin a node
  const handleNodeClick = useCallback((node: GraphNode) => {
    onNodeClick?.(node);
  }, [onNodeClick]);

  // Right-click or ctrl-click to release a pinned node
  const handleContextMenu = useCallback((node: GraphNode) => {
    node.fx = undefined;
    node.fy = undefined;
  }, []);

  // ── Node rendering ────────────────────────────────────────────────────────
  const drawNode = useCallback((node: GraphNode, ctx: CanvasRenderingContext2D, gs: number) => {
    const x = node.x ?? 0;
    const y = node.y ?? 0;
    const isAnchor = anchorNodes.includes(node.id);
    const isVisited = visitedSet.has(node.id);
    const isActive = animating && traversalPath.length > 0;
    const r = (BASE_R[node.type] ?? 10) * (isAnchor ? 1.5 : isVisited ? 1.2 : 1);
    const color = PALETTE[node.type] ?? '#6b7280';

    // Outer glow for anchors
    if (isAnchor) {
      const grd = ctx.createRadialGradient(x, y, r, x, y, r + 14);
      grd.addColorStop(0, color + '55');
      grd.addColorStop(1, 'transparent');
      ctx.beginPath();
      ctx.arc(x, y, r + 14, 0, 2 * Math.PI);
      ctx.fillStyle = grd;
      ctx.fill();
    } else if (isVisited) {
      const grd = ctx.createRadialGradient(x, y, r * 0.5, x, y, r + 8);
      grd.addColorStop(0, color + '33');
      grd.addColorStop(1, 'transparent');
      ctx.beginPath();
      ctx.arc(x, y, r + 8, 0, 2 * Math.PI);
      ctx.fillStyle = grd;
      ctx.fill();
    }

    // Node circle
    ctx.beginPath();
    ctx.arc(x, y, r, 0, 2 * Math.PI);

    if (isActive && !isVisited && !isAnchor) {
      // Faded non-visited nodes during traversal
      ctx.fillStyle = '#1c2128';
      ctx.strokeStyle = '#30363d';
    } else {
      ctx.fillStyle = color + (isAnchor ? 'ff' : isVisited ? 'ee' : 'cc');
      ctx.strokeStyle = isAnchor ? '#fff' : color + '66';
    }
    ctx.lineWidth = isAnchor ? 2.5 : 1.5;
    ctx.fill();
    ctx.stroke();

    // Label
    const showLabel = gs > 0.9 || isVisited || isAnchor;
    if (showLabel) {
      const label = node.name.length > 20 ? node.name.slice(0, 18) + '…' : node.name;
      const fs = Math.max(7, 11 / gs);
      ctx.font = `${isAnchor ? 600 : 400} ${fs}px Inter, sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'top';
      // text shadow
      ctx.fillStyle = '#000a';
      ctx.fillText(label, x + 0.5, y + r + 4 / gs + 0.5);
      ctx.fillStyle = isAnchor ? '#fff' : isVisited ? '#e2e8f0' : '#94a3b8';
      ctx.fillText(label, x, y + r + 4 / gs);
    }

    // Pinned indicator (tiny dot)
    if (node.fx !== undefined) {
      ctx.beginPath();
      ctx.arc(x + r - 3, y - r + 3, 3, 0, 2 * Math.PI);
      ctx.fillStyle = '#f59e0b';
      ctx.fill();
    }
  }, [anchorNodes, visitedSet, animating, traversalPath]);

  // Hit-area for clicks/drag (must match node visual radius)
  const drawPointerArea = useCallback((node: GraphNode, color: string, ctx: CanvasRenderingContext2D) => {
    const r = (BASE_R[node.type] ?? 10) * 1.6;
    ctx.beginPath();
    ctx.arc(node.x ?? 0, node.y ?? 0, r, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();
  }, []);

  // ── Link rendering ────────────────────────────────────────────────────────
  const drawLink = useCallback((link: GraphLink, ctx: CanvasRenderingContext2D, gs: number) => {
    const s = link.source as GraphNode;
    const t = link.target as GraphNode;
    if (!s?.x || !t?.x) return;

    const sid = s.id;
    const tid = t.id;
    const active = visitedSet.has(sid) && visitedSet.has(tid);
    const isAnimating = animating && traversalPath.length > 0;

    if (isAnimating && !active) {
      // Barely visible during traversal
      ctx.beginPath();
      ctx.moveTo(s.x!, s.y!);
      ctx.lineTo(t.x!, t.y!);
      ctx.strokeStyle = 'rgba(255,255,255,0.04)';
      ctx.lineWidth = 0.5;
      ctx.stroke();
      return;
    }

    // Curved path
    const dx = (t.x ?? 0) - (s.x ?? 0);
    const dy = (t.y ?? 0) - (s.y ?? 0);
    const len = Math.sqrt(dx * dx + dy * dy) || 1;
    const mx = ((s.x ?? 0) + (t.x ?? 0)) / 2;
    const my = ((s.y ?? 0) + (t.y ?? 0)) / 2;
    const curvature = active ? 22 : 12;
    const cpx = mx + (-dy / len) * curvature;
    const cpy = my + (dx / len) * curvature;

    ctx.beginPath();
    ctx.moveTo(s.x!, s.y!);
    ctx.quadraticCurveTo(cpx, cpy, t.x!, t.y!);

    if (active) {
      ctx.strokeStyle = 'rgba(88,166,255,0.9)';
      ctx.lineWidth = 2.5;
    } else {
      ctx.strokeStyle = 'rgba(255,255,255,0.15)';
      ctx.lineWidth = 0.8;
    }
    ctx.stroke();

    // Arrowhead on active links
    if (active) {
      const angle = Math.atan2((t.y ?? 0) - cpy, (t.x ?? 0) - cpx);
      const ar = BASE_R[t.type] ?? 10;
      const ax = (t.x ?? 0) - ar * Math.cos(angle);
      const ay = (t.y ?? 0) - ar * Math.sin(angle);
      ctx.beginPath();
      ctx.moveTo(ax, ay);
      ctx.lineTo(ax - 7 * Math.cos(angle - 0.4), ay - 7 * Math.sin(angle - 0.4));
      ctx.lineTo(ax - 7 * Math.cos(angle + 0.4), ay - 7 * Math.sin(angle + 0.4));
      ctx.closePath();
      ctx.fillStyle = 'rgba(88,166,255,0.9)';
      ctx.fill();
    }

    // Edge label on active links when zoomed in
    if (active && gs > 0.6) {
      const label = link.relationship.replace(/_/g, ' ');
      const fs = Math.max(6, 9 / gs);
      ctx.font = `${fs}px JetBrains Mono, monospace`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = '#000a';
      ctx.fillText(label, cpx + 0.5, cpy + 0.5);
      ctx.fillStyle = 'rgba(88,166,255,0.85)';
      ctx.fillText(label, cpx, cpy);
    }
  }, [visitedSet, animating, traversalPath]);

  // ── Zoom controls ─────────────────────────────────────────────────────────
  const zoomIn  = () => fgRef.current?.zoom(fgRef.current.zoom() * 1.3, 250);
  const zoomOut = () => fgRef.current?.zoom(fgRef.current.zoom() * 0.77, 250);
  const fitAll  = () => fgRef.current?.zoomToFit(400, 40);

  const releaseAll = () => {
    layoutData.nodes.forEach((n) => { n.fx = undefined; n.fy = undefined; });
    fgRef.current?.d3ReheatSimulation();
  };

  return (
    <div className="w-full h-full relative overflow-hidden bg-[#0d1117]">
      {/* Graph */}
      <ForceGraph2D
        ref={fgRef}
        graphData={layoutData}
        nodeId="id"
        nodeCanvasObject={drawNode}
        nodeCanvasObjectMode={() => 'replace'}
        nodePointerAreaPaint={drawPointerArea}
        linkCanvasObject={drawLink}
        linkCanvasObjectMode={() => 'replace'}
        onNodeClick={handleNodeClick}
        onNodeDrag={handleNodeDrag}
        onNodeDragEnd={handleNodeDragEnd}
        onNodeRightClick={handleContextMenu}
        enableNodeDrag={true}
        backgroundColor="#0d1117"
        cooldownTicks={200}
        d3AlphaDecay={0.015}
        d3VelocityDecay={0.35}
        warmupTicks={80}
        nodeLabel={(n) => (n as GraphNode).name}
        linkLabel={(l) => (l as GraphLink).relationship}
      />

      {/* Legend */}
      <div className="absolute top-3 left-3 z-10 flex flex-wrap gap-1 max-w-[200px] pointer-events-none">
        {Object.entries(PALETTE).map(([type, color]) => (
          <span
            key={type}
            className="flex items-center gap-1 text-[9px] text-gray-400 bg-black/50 backdrop-blur px-1.5 py-0.5 rounded-full"
          >
            <span className="w-2 h-2 rounded-full" style={{ background: color }} />
            {type}
          </span>
        ))}
      </div>

      {/* Traversal indicator */}
      {animating && traversalPath.length > 0 && (
        <div className="absolute bottom-12 left-1/2 -translate-x-1/2 z-10 bg-[#161b22]/90 backdrop-blur border border-[#30363d] rounded-full px-4 py-1.5 text-xs text-[#58a6ff] pointer-events-none">
          Tracing the connection… {Math.min(animStep, traversalPath.length)}/{traversalPath.length}
        </div>
      )}

      {/* Drag hint */}
      {hint && layoutData.nodes.length > 0 && (
        <div className="absolute bottom-12 right-3 z-10 bg-black/60 backdrop-blur text-[10px] text-gray-400 px-3 py-1.5 rounded-lg pointer-events-none transition-opacity">
          Drag to rearrange · Click any dot for details
        </div>
      )}

      {/* Zoom / layout controls */}
      <div className="absolute bottom-3 right-3 z-10 flex flex-col gap-1">
        {[
          { label: '+', action: zoomIn,    title: 'Zoom in' },
          { label: '−', action: zoomOut,   title: 'Zoom out' },
          { label: '⊡', action: fitAll,    title: 'Fit all nodes' },
          { label: '↺', action: releaseAll,title: 'Release all pins & re-simulate' },
        ].map(({ label, action, title }) => (
          <button
            key={label}
            onClick={action}
            title={title}
            className="w-8 h-8 bg-[#161b22] hover:bg-[#21262d] border border-[#30363d] rounded text-gray-300 text-sm font-mono flex items-center justify-center transition-colors"
          >
            {label}
          </button>
        ))}
      </div>

      {/* Empty state */}
      {layoutData.nodes.length === 0 && (
        <div className="absolute inset-0 flex flex-col items-center justify-center text-gray-600 pointer-events-none gap-2">
          <span className="text-4xl">🐾</span>
          <p className="text-sm">Load records (Records tab) to see your pet's health map</p>
        </div>
      )}
    </div>
  );
}
