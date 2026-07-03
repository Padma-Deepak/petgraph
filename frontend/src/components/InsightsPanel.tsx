import { useEffect, useState } from 'react';
import { dismissInsight, fetchInsights } from '../api/client';
import type { Insight } from '../types';

const KIND_ICON: Record<string, string> = {
  recurring_pattern: '🔁',
  overdue_vaccine: '💉',
  checkup_gap: '🩺',
  life_stage: '🎂',
};

interface Props {
  onChanged?: () => void;
}

export default function InsightsPanel({ onChanged }: Props) {
  const [insights, setInsights] = useState<Insight[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [openWhy, setOpenWhy] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  async function load() {
    try {
      const data = await fetchInsights();
      setInsights(data.insights);
    } finally {
      setLoaded(true);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function handleDismiss(id: string) {
    setBusy(id);
    try {
      await dismissInsight(id);
      await load();
      onChanged?.();
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="max-w-2xl mx-auto w-full p-6 flex flex-col gap-4">
      <div>
        <h2 className="text-lg font-semibold text-white">Worth knowing</h2>
        <p className="text-xs text-gray-500 mt-0.5">
          Patterns and suggestions spotted by looking across your pets' whole history — no question needed.
        </p>
      </div>

      {loaded && insights.length === 0 && (
        <div className="text-center py-12 text-gray-600">
          <span className="text-3xl block mb-2">🌱</span>
          <p className="text-sm">Nothing flagged right now. New observations appear as records build up.</p>
        </div>
      )}

      {insights.map((ins) => (
        <div key={ins.id} className="border border-[#30363d] bg-[#161b22] rounded-xl p-4 animate-fade-in">
          <div className="flex gap-3 items-start">
            <span className="text-xl leading-none mt-0.5">{KIND_ICON[ins.kind] ?? '💡'}</span>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-sm font-medium text-white">{ins.title}</span>
                {ins.source === 'pet_records' ? (
                  <span className="text-[9px] uppercase tracking-wide bg-[#1f6feb]/25 text-[#79b8ff] px-1.5 py-0.5 rounded">
                    From {ins.pet_name ?? 'your pet'}'s records
                  </span>
                ) : (
                  <span className="text-[9px] uppercase tracking-wide bg-violet-900/40 text-violet-300 px-1.5 py-0.5 rounded">
                    General guideline
                  </span>
                )}
              </div>
              {ins.body && <p className="text-xs text-gray-300 mt-1.5 leading-relaxed">{ins.body}</p>}
              {ins.source !== 'pet_records' && (
                <p className="text-[10px] text-gray-600 mt-1">
                  Based on standard veterinary guidance, not on something specific in the medical records.
                </p>
              )}
              {ins.why && (
                <button
                  onClick={() => setOpenWhy(openWhy === ins.id ? null : ins.id)}
                  className="text-[11px] text-[#58a6ff] hover:text-white mt-2 transition-colors"
                >
                  {openWhy === ins.id ? 'Hide' : 'Why was this flagged?'}
                </button>
              )}
              {openWhy === ins.id && ins.why && (
                <p className="text-[11px] text-gray-400 mt-1.5 bg-[#0d1117] border border-[#21262d] rounded-lg p-2.5 leading-relaxed">
                  {ins.why}
                </p>
              )}
            </div>
            <button
              onClick={() => handleDismiss(ins.id)}
              disabled={busy === ins.id}
              className="text-[10px] text-gray-500 hover:text-red-300 shrink-0 transition-colors disabled:opacity-40"
            >
              Dismiss
            </button>
          </div>
        </div>
      ))}
    </div>
  );
}
