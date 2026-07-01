import { useState } from 'react';
import { fetchConflicts } from '../api/client';
import type { Conflict } from '../types';

interface Props {
  onHighlightNodes: (ids: string[]) => void;
}

export default function ConflictPanel({ onHighlightNodes }: Props) {
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [loading, setLoading] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    try {
      const data = await fetchConflicts();
      setConflicts(data.conflicts);
      setLoaded(true);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">
          Conflict Detection
          <span className="ml-1.5 text-[9px] text-gray-600">(rule-based, no LLM)</span>
        </h3>
        <button
          onClick={load}
          disabled={loading}
          className="text-xs text-[#58a6ff] hover:text-white transition-colors disabled:opacity-40"
        >
          {loading ? '…' : loaded ? '↻ refresh' : 'scan'}
        </button>
      </div>

      {loaded && conflicts.length === 0 && (
        <p className="text-xs text-gray-600">No conflicts detected.</p>
      )}

      {conflicts.map((c) => (
        <div
          key={c.conflict_key}
          className={`border rounded-lg overflow-hidden cursor-pointer transition-colors ${
            c.severity === 'high'
              ? 'border-red-800 bg-red-950/30 hover:bg-red-950/50'
              : 'border-yellow-800 bg-yellow-950/20 hover:bg-yellow-950/40'
          }`}
          onClick={() => {
            setExpanded(expanded === c.conflict_key ? null : c.conflict_key);
            onHighlightNodes(c.involved_nodes);
          }}
        >
          <div className="p-2.5 flex items-start gap-2">
            <span className={`text-lg leading-none ${c.severity === 'high' ? 'text-red-400' : 'text-yellow-400'}`}>
              {c.severity === 'high' ? '⚠' : '⚡'}
            </span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-0.5">
                <span className={`text-[9px] font-mono uppercase px-1.5 py-0.5 rounded ${
                  c.severity === 'high' ? 'bg-red-900 text-red-300' : 'bg-yellow-900 text-yellow-300'
                }`}>
                  {c.type.replace(/_/g, ' ')}
                </span>
                {c.medication && <span className="text-xs font-semibold text-white">{c.medication}</span>}
                {c.vaccine && <span className="text-xs font-semibold text-white">{c.vaccine} vaccine</span>}
              </div>
              <p className="text-xs text-gray-300 leading-relaxed">{c.description}</p>
            </div>
          </div>

          {expanded === c.conflict_key && (
            <div className="border-t border-[#30363d] p-2.5 bg-[#0d1117]">
              <p className="text-[10px] text-gray-400 mb-1 font-semibold uppercase tracking-wider">
                Suggested Question for Your Vet
              </p>
              <p className="text-xs text-[#58a6ff] leading-relaxed italic">
                "{c.suggested_question}"
              </p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
