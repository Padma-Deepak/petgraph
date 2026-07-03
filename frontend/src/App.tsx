import { useCallback, useEffect, useRef, useState } from 'react';
import { fetchConflicts, fetchGraph, fetchInsights, fetchPetSubgraph, fetchReminders } from './api/client';
import GraphCanvas from './components/GraphCanvas';
import DocumentUpload from './components/DocumentUpload';
import AskPanel from './components/AskPanel';
import ConflictPanel from './components/ConflictPanel';
import PreVisitSummary from './components/PreVisitSummary';
import NodeDetailPanel from './components/NodeDetailPanel';
import RemindersPanel from './components/RemindersPanel';
import InsightsPanel from './components/InsightsPanel';
import type { GraphData, GraphNode, QueryResult } from './types';

type View = 'ask' | 'map' | 'reminders' | 'insights' | 'alerts' | 'visit' | 'records';

interface Counts {
  reminders: number;
  overdue: number;
  insights: number;
  alerts: number;
}

export default function App() {
  const [view, setView] = useState<View>('ask');
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], links: [] });
  const [subgraph, setSubgraph] = useState<GraphData | null>(null);
  const [filterPetId, setFilterPetId] = useState<string | null>(null);
  const [lastResult, setLastResult] = useState<QueryResult | null>(null);
  const [animating, setAnimating] = useState(false);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [counts, setCounts] = useState<Counts>({ reminders: 0, overdue: 0, insights: 0, alerts: 0 });
  const animTimerRef = useRef<ReturnType<typeof setTimeout>>();

  const loadGraph = useCallback(async () => {
    try {
      const data = await fetchGraph();
      setGraphData(data);
    } catch (e) {
      console.error('Failed to load graph', e);
    }
  }, []);

  const refreshCounts = useCallback(async () => {
    const [r, i, c] = await Promise.allSettled([fetchReminders(), fetchInsights(), fetchConflicts()]);
    setCounts({
      reminders: r.status === 'fulfilled' ? r.value.count : 0,
      overdue: r.status === 'fulfilled' ? r.value.overdue_count : 0,
      insights: i.status === 'fulfilled' ? i.value.count : 0,
      alerts: c.status === 'fulfilled' ? (c.value.conflicts?.length ?? 0) : 0,
    });
  }, []);

  useEffect(() => {
    loadGraph();
    refreshCounts();
  }, [loadGraph, refreshCounts]);

  // Per-pet filtering is served by the backend (Cognee graph query), not client BFS.
  useEffect(() => {
    if (!filterPetId) {
      setSubgraph(null);
      return;
    }
    let cancelled = false;
    fetchPetSubgraph(filterPetId)
      .then((data) => { if (!cancelled) setSubgraph(data); })
      .catch(() => { if (!cancelled) setSubgraph(null); });
    return () => { cancelled = true; };
  }, [filterPetId, graphData]);

  const displayGraph = filterPetId && subgraph ? subgraph : graphData;
  const pets = graphData.nodes.filter((n) => n.type === 'pet');
  const hasRecords = graphData.nodes.length > 0;

  function handleGraphUpdate() {
    loadGraph();
    refreshCounts();
  }

  function startAnimation(result: QueryResult) {
    setAnimating(true);
    clearTimeout(animTimerRef.current);
    animTimerRef.current = setTimeout(
      () => setAnimating(false),
      result.traversal_path.length * 240 + 500,
    );
  }

  function handleShowMap(result: QueryResult) {
    setLastResult(result);
    setFilterPetId(null);
    setView('map');
    startAnimation(result);
  }

  const NAV: { id: View; label: string; badge?: number; badgeUrgent?: boolean }[] = [
    { id: 'ask', label: 'Ask' },
    { id: 'map', label: 'Health map' },
    { id: 'reminders', label: 'Reminders', badge: counts.reminders, badgeUrgent: counts.overdue > 0 },
    { id: 'insights', label: 'Worth knowing', badge: counts.insights },
    { id: 'alerts', label: 'Alerts', badge: counts.alerts, badgeUrgent: counts.alerts > 0 },
    { id: 'visit', label: 'Visit prep' },
    { id: 'records', label: 'Records' },
  ];

  return (
    <div className="h-screen w-screen flex flex-col overflow-hidden font-[Inter,sans-serif]">
      {/* Header: brand + navigation */}
      <header className="flex items-center justify-between px-4 border-b border-[#30363d] bg-[#161b22] shrink-0">
        <button onClick={() => setView('ask')} className="flex items-center gap-2 py-2.5">
          <span className="text-xl">🐾</span>
          <span className="text-sm font-bold text-white tracking-tight">PetGraph</span>
        </button>
        <nav className="flex items-center gap-0.5 overflow-x-auto">
          {NAV.map((item) => (
            <button
              key={item.id}
              onClick={() => setView(item.id)}
              className={`relative px-3 py-3 text-xs font-medium whitespace-nowrap transition-colors border-b-2 ${
                view === item.id
                  ? 'text-white border-[#58a6ff]'
                  : 'text-gray-500 border-transparent hover:text-gray-300'
              }`}
            >
              {item.label}
              {item.badge != null && item.badge > 0 && (
                <span
                  className={`ml-1.5 inline-flex items-center justify-center text-[9px] font-semibold rounded-full px-1.5 py-px align-middle ${
                    item.badgeUrgent ? 'bg-red-900/80 text-red-200' : 'bg-[#30363d] text-gray-300'
                  }`}
                >
                  {item.badge}
                </span>
              )}
            </button>
          ))}
        </nav>
      </header>

      {/* Main content */}
      <main className="flex-1 overflow-hidden bg-[#0d1117]">
        {view === 'ask' && (
          <AskPanel onResult={setLastResult} onShowMap={handleShowMap} hasRecords={hasRecords} />
        )}

        {view === 'map' && (
          <div className="h-full flex flex-col">
            {/* Pet filter chips */}
            <div className="flex items-center gap-2 px-4 py-2 border-b border-[#21262d] shrink-0 flex-wrap">
              <span className="text-[10px] text-gray-600 uppercase tracking-wider">Showing</span>
              <button
                onClick={() => setFilterPetId(null)}
                className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                  !filterPetId
                    ? 'bg-[#1f6feb]/20 border-[#1f6feb]/50 text-white'
                    : 'border-[#30363d] text-gray-500 hover:text-gray-300'
                }`}
              >
                Everyone
              </button>
              {pets.map((pet) => (
                <button
                  key={pet.id}
                  onClick={() => setFilterPetId(filterPetId === pet.id ? null : pet.id)}
                  className={`text-xs px-3 py-1 rounded-full border transition-colors ${
                    filterPetId === pet.id
                      ? 'bg-[#1f6feb]/20 border-[#1f6feb]/50 text-white'
                      : 'border-[#30363d] text-gray-500 hover:text-gray-300'
                  }`}
                >
                  🐾 {pet.name}
                </button>
              ))}
              <span className="text-[10px] text-gray-600 ml-auto">
                {displayGraph.nodes.length > 0 &&
                  `${displayGraph.nodes.length} connected records · click any dot for details`}
              </span>
            </div>
            <div className="flex-1 relative overflow-hidden">
              <GraphCanvas
                data={displayGraph}
                traversalPath={lastResult?.traversal_path ?? []}
                anchorNodes={lastResult?.anchor_nodes ?? []}
                animating={animating}
                onNodeClick={(node: GraphNode) => setSelectedNodeId(node.id)}
              />
            </div>
          </div>
        )}

        {view === 'reminders' && (
          <div className="h-full overflow-y-auto">
            <RemindersPanel onChanged={refreshCounts} />
          </div>
        )}

        {view === 'insights' && (
          <div className="h-full overflow-y-auto">
            <InsightsPanel onChanged={refreshCounts} />
          </div>
        )}

        {view === 'alerts' && (
          <div className="h-full overflow-y-auto">
            <div className="max-w-2xl mx-auto w-full p-6">
              <ConflictPanel onHighlightNodes={() => {}} />
            </div>
          </div>
        )}

        {view === 'visit' && (
          <div className="h-full overflow-y-auto">
            <div className="max-w-2xl mx-auto w-full p-6">
              <PreVisitSummary />
            </div>
          </div>
        )}

        {view === 'records' && (
          <div className="h-full overflow-y-auto">
            <div className="max-w-2xl mx-auto w-full p-6 flex flex-col gap-4">
              <div>
                <h2 className="text-lg font-semibold text-white">Records</h2>
                <p className="text-xs text-gray-500 mt-0.5">
                  Add visit summaries, discharge notes, or your own notes — everything gets connected automatically.
                </p>
              </div>
              <DocumentUpload onGraphUpdate={handleGraphUpdate} />
            </div>
          </div>
        )}
      </main>

      {/* Node detail overlay */}
      <NodeDetailPanel nodeId={selectedNodeId} onClose={() => setSelectedNodeId(null)} />
    </div>
  );
}
