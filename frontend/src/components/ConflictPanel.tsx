import { useEffect, useState } from 'react';
import { fetchConflicts } from '../api/client';
import type { Conflict } from '../types';

const TYPE_LABEL: Record<Conflict['type'], string> = {
  medication_status: 'Medication mismatch',
  vaccine_record_mismatch: 'Vaccine records disagree',
};

interface Props {
  onHighlightNodes: (ids: string[]) => void;
}

export default function ConflictPanel({ onHighlightNodes }: Props) {
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  useEffect(() => {
    fetchConflicts()
      .then((data) => setConflicts(data.conflicts))
      .catch(() => {})
      .finally(() => setLoaded(true));
  }, []);

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold text-white">Alerts</h2>
        <p className="text-xs text-gray-500 mt-0.5">
          Places where your providers' records don't agree with each other — checked automatically, worth
          clearing up at your next visit.
        </p>
      </div>

      {loaded && conflicts.length === 0 && (
        <div className="text-center py-12 text-gray-600">
          <span className="text-3xl block mb-2">👍</span>
          <p className="text-sm">All your providers' records agree with each other.</p>
        </div>
      )}

      {conflicts.map((c) => (
        <div
          key={c.conflict_key}
          className={`border rounded-xl overflow-hidden cursor-pointer transition-colors animate-fade-in ${
            c.severity === 'high'
              ? 'border-red-800 bg-red-950/30 hover:bg-red-950/50'
              : 'border-yellow-800 bg-yellow-950/20 hover:bg-yellow-950/40'
          }`}
          onClick={() => {
            setExpanded(expanded === c.conflict_key ? null : c.conflict_key);
            onHighlightNodes(c.involved_nodes);
          }}
        >
          <div className="p-4 flex items-start gap-3">
            <span className={`text-lg leading-none ${c.severity === 'high' ? 'text-red-400' : 'text-yellow-400'}`}>
              {c.severity === 'high' ? '⚠' : '⚡'}
            </span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1 flex-wrap">
                <span
                  className={`text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded ${
                    c.severity === 'high' ? 'bg-red-900 text-red-300' : 'bg-yellow-900 text-yellow-300'
                  }`}
                >
                  {TYPE_LABEL[c.type] ?? 'Records disagree'}
                </span>
                {c.medication && <span className="text-xs font-semibold text-white">{c.medication}</span>}
                {c.vaccine && <span className="text-xs font-semibold text-white">{c.vaccine} vaccine</span>}
                {c.pet && <span className="text-[10px] text-gray-500">· {c.pet}</span>}
              </div>
              <p className="text-xs text-gray-300 leading-relaxed">{c.description}</p>
              <p className="text-[10px] text-gray-600 mt-1.5">
                {expanded === c.conflict_key ? 'Hide suggestion' : 'Tap for what to ask your vet'}
              </p>
            </div>
          </div>

          {expanded === c.conflict_key && (
            <div className="border-t border-[#30363d] p-4 bg-[#0d1117]">
              <p className="text-[10px] text-gray-400 mb-1 font-semibold uppercase tracking-wider">
                Ask your vet
              </p>
              <p className="text-xs text-[#79b8ff] leading-relaxed italic">"{c.suggested_question}"</p>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
