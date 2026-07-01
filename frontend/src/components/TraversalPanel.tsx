import { useState } from 'react';
import { querySymptom } from '../api/client';
import type { QueryResult, Citation } from '../types';

interface Props {
  onTraversalResult: (result: QueryResult) => void;
}

const EXAMPLE_QUERIES = [
  "she's rubbing her ears again",
  "head shaking and ear scratching",
  "what ear issues has Bella had",
  "show me her medication history",
];

export default function TraversalPanel({ onTraversalResult }: Props) {
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState('');

  async function handleQuery(text: string) {
    if (!text.trim()) return;
    setLoading(true);
    setError('');
    setResult(null);
    try {
      const data = await querySymptom(text);
      setResult(data);
      onTraversalResult(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Query failed');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-3 h-full">
      {/* Input */}
      <div className="flex gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleQuery(query)}
          placeholder="Describe a symptom or ask about history…"
          className="flex-1 bg-[#0d1117] border border-[#30363d] focus:border-[#58a6ff] rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 outline-none transition-colors"
        />
        <button
          onClick={() => handleQuery(query)}
          disabled={loading || !query.trim()}
          className="px-3 py-2 bg-[#1f6feb] hover:bg-[#388bfd] disabled:opacity-40 rounded-lg text-sm font-medium transition-colors"
        >
          {loading ? '…' : '→'}
        </button>
      </div>

      {/* Example queries */}
      <div className="flex flex-wrap gap-1">
        {EXAMPLE_QUERIES.map((q) => (
          <button
            key={q}
            onClick={() => { setQuery(q); handleQuery(q); }}
            className="text-[10px] text-gray-500 hover:text-[#58a6ff] bg-[#161b22] hover:bg-[#1f2937] px-2 py-1 rounded transition-colors"
          >
            {q}
          </button>
        ))}
      </div>

      {error && (
        <div className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded p-2">{error}</div>
      )}

      {/* Results */}
      {result && (
        <div className="flex-1 overflow-y-auto flex flex-col gap-3 animate-fade-in">
          {/* Traversal stats */}
          <div className="flex gap-3 text-[10px] text-gray-500">
            <span className="text-[#58a6ff]">{result.anchor_nodes.length} anchor nodes</span>
            <span>→</span>
            <span>{result.traversal_path.length} nodes traversed</span>
            <span>→</span>
            <span>{result.citations.length} citations</span>
          </div>

          {/* Summary */}
          <div className="bg-[#0d1117] border border-[#30363d] rounded-lg p-3">
            <h3 className="text-xs font-semibold text-gray-400 mb-2 uppercase tracking-wider">
              Longitudinal Summary
            </h3>
            <p className="text-sm text-gray-200 leading-relaxed">{result.summary}</p>
          </div>

          {/* Citations */}
          {result.citations.length > 0 && (
            <div className="bg-[#0d1117] border border-[#30363d] rounded-lg p-3">
              <h3 className="text-xs font-semibold text-gray-400 mb-2 uppercase tracking-wider">
                Sources & Citations
              </h3>
              <div className="flex flex-col gap-1.5">
                {result.citations.map((c: Citation, i: number) => (
                  <div key={i} className="flex items-start gap-2 text-xs">
                    <span
                      className="shrink-0 px-1.5 py-0.5 rounded text-[9px] font-mono uppercase"
                      style={{ background: typeColor(c.type) + '33', color: typeColor(c.type) }}
                    >
                      {c.type}
                    </span>
                    <span className="text-gray-300">{c.entity}</span>
                    {c.date && <span className="text-gray-500 ml-auto shrink-0">{c.date}</span>}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {!result && !loading && (
        <div className="flex-1 flex items-center justify-center text-xs text-gray-600 text-center">
          Type a symptom or question above.<br />
          The graph will animate the traversal path.
        </div>
      )}

      {loading && (
        <div className="flex-1 flex flex-col items-center justify-center gap-2 text-xs text-[#58a6ff]">
          <div className="w-6 h-6 border-2 border-[#58a6ff] border-t-transparent rounded-full animate-spin" />
          Searching knowledge graph…
        </div>
      )}
    </div>
  );
}

function typeColor(type: string): string {
  const map: Record<string, string> = {
    symptom: '#fb7185', diagnosis: '#f97316', medication: '#4ade80',
    vaccine: '#22d3ee', visit: '#34d399', provider: '#a78bfa',
  };
  return map[type] ?? '#6b7280';
}
