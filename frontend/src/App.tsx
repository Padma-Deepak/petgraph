import { useCallback, useEffect, useRef, useState } from 'react';
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
  const animTimerRef = useRef<ReturnType<typeof setTimeout>>();

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
            <span className="text-[#58a6ff] font-semibold">{nodeCount}</span> nodes
          </span>
          <span>
            <span className="text-[#58a6ff] font-semibold">{edgeCount}</span> edges
          </span>
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
            <h2 className="text-[10px] font-semibold text-gray-400 uppercase tracking-wider mb-2">
              Pets in graph
            </h2>
            <div className="flex flex-col gap-1">
              {graphData.nodes
                .filter((n) => n.type === 'pet')
                .map((pet) => (
                  <button
                    key={pet.id}
                    onClick={() => setSelectedNodeId(pet.id)}
                    className="flex items-center gap-2 text-xs text-left px-2 py-1.5 rounded hover:bg-[#21262d] transition-colors"
                  >
                    <span className="w-2 h-2 rounded-full bg-[#f5a623] shrink-0" />
                    <div>
                      <div className="text-gray-200">{pet.name}</div>
                      <div className="text-[9px] text-gray-600">
                        {String(pet.properties?.breed ?? '')} · {String(pet.properties?.species ?? '')}
                      </div>
                    </div>
                  </button>
                ))}
              {graphData.nodes.filter((n) => n.type === 'pet').length === 0 && (
                <p className="text-[10px] text-gray-600">Load seed data to see pets</p>
              )}
            </div>
          </div>
        </aside>

        {/* Center: graph canvas */}
        <main className="flex-1 relative overflow-hidden">
          <GraphCanvas
            data={graphData}
            traversalPath={traversalResult?.traversal_path ?? []}
            anchorNodes={traversalResult?.anchor_nodes ?? []}
            animating={animating}
            onNodeClick={(node: GraphNode) => setSelectedNodeId(node.id)}
          />
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
