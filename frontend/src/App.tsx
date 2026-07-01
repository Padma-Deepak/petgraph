import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { fetchGraph } from './api/client';
import GraphCanvas from './components/GraphCanvas';
import DocumentUpload from './components/DocumentUpload';
import TraversalPanel from './components/TraversalPanel';
import ConflictPanel from './components/ConflictPanel';
import PreVisitSummary from './components/PreVisitSummary';
import NodeDetailPanel from './components/NodeDetailPanel';
import type { GraphData, GraphNode, QueryResult } from './types';

type Tab = 'query' | 'conflicts' | 'summary';

export default function App() {
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], links: [] });
  const [traversalResult, setTraversalResult] = useState<QueryResult | null>(null);
  const [animating, setAnimating] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [activeTab, setActiveTab] = useState<Tab>('query');
  const [nodeCount, setNodeCount] = useState(0);
  const [edgeCount, setEdgeCount] = useState(0);
  const [filterPetId, setFilterPetId] = useState<string | null>(null);
  const animTimerRef = useRef<ReturnType<typeof setTimeout>>();

  // Directed BFS from a pet node — follows edges source→target only so
  // Bella's and Charlie's subgraphs stay separate despite sharing an owner.
  const displayGraph = useMemo(() => {
    if (!filterPetId) return graphData;

    const fwdAdj: Record<string, string[]> = {};
    for (const link of graphData.links) {
      const s = typeof link.source === 'object' ? (link.source as GraphNode).id : link.source as string;
      const t = typeof link.target === 'object' ? (link.target as GraphNode).id : link.target as string;
      (fwdAdj[s] ??= []).push(t);
    }

    const visited = new Set<string>();
    const queue = [filterPetId];
    while (queue.length) {
      const id = queue.shift()!;
      if (visited.has(id)) continue;
      visited.add(id);
      for (const nb of fwdAdj[id] ?? []) queue.push(nb);
    }

    return {
      nodes: graphData.nodes.filter((n) => visited.has(n.id)),
      links: graphData.links.filter((l) => {
        const s = typeof l.source === 'object' ? (l.source as GraphNode).id : l.source as string;
        const t = typeof l.target === 'object' ? (l.target as GraphNode).id : l.target as string;
        return visited.has(s) && visited.has(t);
      }),
    };
  }, [graphData, filterPetId]);

  const loadGraph = useCallback(async () => {
    try {
      const data = await fetchGraph();
      setGraphData(data);
      setNodeCount(data.nodes.length);
      setEdgeCount(data.links.length);
    } catch (e) {
      console.error('Failed to load graph', e);
    }
  }, []);

  useEffect(() => {
    loadGraph();
  }, [loadGraph]);

  function handleTraversalResult(result: QueryResult) {
    // Merge traversal subgraph into full graph for display
    setTraversalResult(result);
    // anchor_nodes highlighted via traversalResult prop
    setAnimating(true);

    clearTimeout(animTimerRef.current);
    animTimerRef.current = setTimeout(() => setAnimating(false), result.traversal_path.length * 240 + 500);
  }

  function handleHighlightNodes(_ids: string[]) {
    setActiveTab('conflicts');
  }

  const TABS: { id: Tab; label: string }[] = [
    { id: 'query', label: 'Query Graph' },
    { id: 'conflicts', label: 'Conflicts' },
    { id: 'summary', label: 'Pre-Visit' },
  ];

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden font-[Inter,sans-serif]">
      {/* Header */}
      <header className="flex items-center justify-between px-4 py-2 border-b border-[#30363d] bg-[#161b22] shrink-0">
        <div className="flex items-center gap-3">
          <span className="text-xl">🐾</span>
          <div>
            <h1 className="text-sm font-bold text-white tracking-tight">PetGraph</h1>
            <p className="text-[9px] text-gray-500">Unified Pet Health Record · Powered by Cognee</p>
          </div>
        </div>
        <div className="flex items-center gap-4 text-[10px] text-gray-500 font-mono">
          <span>
            <span className="text-[#58a6ff] font-semibold">
              {filterPetId ? displayGraph.nodes.length : nodeCount}
            </span>
            {filterPetId ? <span className="text-gray-600">/{nodeCount}</span> : null}
            {' '}nodes
          </span>
          <span>
            <span className="text-[#58a6ff] font-semibold">
              {filterPetId ? displayGraph.links.length : edgeCount}
            </span>
            {' '}edges
          </span>
          {filterPetId && (
            <span className="text-[#f5a623]">● filtered</span>
          )}
          {animating && (
            <span className="text-[#f5a623] animate-pulse">● traversing</span>
          )}
        </div>
      </header>

      {/* Main layout */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left sidebar: documents */}
        <aside className="w-64 shrink-0 border-r border-[#30363d] bg-[#161b22] flex flex-col overflow-hidden">
          <div className="p-3 border-b border-[#30363d]">
            <h2 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-3">
              Documents
            </h2>
            <DocumentUpload onGraphUpdate={loadGraph} />
          </div>

          {/* Pet list */}
          <div className="flex-1 overflow-y-auto p-3">
            <div className="flex items-center justify-between mb-2">
              <h2 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider">
                Pets in graph
              </h2>
              {filterPetId && (
                <button
                  onClick={() => setFilterPetId(null)}
                  className="text-[9px] text-[#58a6ff] hover:text-white transition-colors"
                >
                  show all
                </button>
              )}
            </div>
            <div className="flex flex-col gap-1">
              {graphData.nodes
                .filter((n) => n.type === 'pet')
                .map((pet) => {
                  const isActive = filterPetId === pet.id;
                  const petNodeCount = (() => {
                    if (!isActive) return null;
                    return displayGraph.nodes.length;
                  })();
                  return (
                    <button
                      key={pet.id}
                      onClick={() => {
                        setFilterPetId(isActive ? null : pet.id);
                        setSelectedNodeId(pet.id);
                      }}
                      className={`flex items-center gap-2 text-xs text-left px-2 py-1.5 rounded transition-colors ${
                        isActive
                          ? 'bg-[#1f6feb]/20 border border-[#1f6feb]/40 text-white'
                          : 'hover:bg-[#21262d] text-gray-200'
                      }`}
                    >
                      <span className={`w-2 h-2 rounded-full shrink-0 ${isActive ? 'bg-[#58a6ff]' : 'bg-[#f5a623]'}`} />
                      <div className="flex-1 min-w-0">
                        <div className="font-medium">{pet.name}</div>
                        <div className="text-[9px] text-gray-500">
                          {String(pet.properties?.breed ?? '')} · {String(pet.properties?.species ?? '')}
                        </div>
                      </div>
                      {isActive && petNodeCount !== null && (
                        <span className="text-[9px] text-[#58a6ff] font-mono shrink-0">{petNodeCount}n</span>
                      )}
                    </button>
                  );
                })}
              {graphData.nodes.filter((n) => n.type === 'pet').length === 0 && (
                <p className="text-[10px] text-gray-600">Load seed data to see pets</p>
              )}
            </div>

            {/* Multi-pet separation note */}
            {graphData.nodes.filter((n) => n.type === 'pet').length > 1 && (
              <p className="text-[9px] text-gray-600 mt-3 leading-relaxed">
                Click a pet to isolate its subgraph.{' '}
                {filterPetId ? 'Directed traversal keeps records separate despite shared owner.' : ''}
              </p>
            )}
          </div>
        </aside>

        {/* Center: graph canvas */}
        <main className="flex-1 relative overflow-hidden">
          <GraphCanvas
            data={displayGraph}
            traversalPath={traversalResult?.traversal_path ?? []}
            anchorNodes={traversalResult?.anchor_nodes ?? []}
            animating={animating}
            onNodeClick={(node: GraphNode) => setSelectedNodeId(node.id)}
          />
          {filterPetId && (
            <div className="absolute top-3 left-3 flex items-center gap-2 bg-[#161b22]/90 border border-[#1f6feb]/50 rounded-lg px-3 py-1.5 text-xs backdrop-blur-sm">
              <span className="text-[#58a6ff]">
                Showing: <span className="font-semibold text-white">
                  {graphData.nodes.find(n => n.id === filterPetId)?.name ?? filterPetId}
                </span>
              </span>
              <span className="text-gray-600">·</span>
              <span className="text-gray-500">{displayGraph.nodes.length} nodes</span>
              <button
                onClick={() => setFilterPetId(null)}
                className="text-gray-500 hover:text-white ml-1 transition-colors"
                title="Show all pets"
              >
                ✕
              </button>
            </div>
          )}
        </main>

        {/* Right sidebar: query / conflicts / summary */}
        <aside className="w-80 shrink-0 border-l border-[#30363d] bg-[#161b22] flex flex-col overflow-hidden">
          {/* Tabs */}
          <div className="flex border-b border-[#30363d] shrink-0">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex-1 py-2.5 text-[11px] font-medium transition-colors ${
                  activeTab === tab.id
                    ? 'text-white border-b-2 border-[#58a6ff]'
                    : 'text-gray-500 hover:text-gray-300'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          <div className="flex-1 overflow-y-auto p-3">
            {activeTab === 'query' && (
              <TraversalPanel onTraversalResult={handleTraversalResult} />
            )}
            {activeTab === 'conflicts' && (
              <ConflictPanel onHighlightNodes={handleHighlightNodes} />
            )}
            {activeTab === 'summary' && (
              <PreVisitSummary />
            )}
          </div>
        </aside>
      </div>

      {/* Node detail overlay */}
      <NodeDetailPanel
        nodeId={selectedNodeId}
        onClose={() => setSelectedNodeId(null)}
      />
    </div>
  );
}
