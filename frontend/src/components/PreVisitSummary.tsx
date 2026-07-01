import { useEffect, useState } from 'react';
import { fetchProviders, fetchSummary } from '../api/client';

interface Provider { id: string; name: string; properties: Record<string, unknown> }

export default function PreVisitSummary() {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [selected, setSelected] = useState('');
  const [summary, setSummary] = useState<Record<string, unknown> | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchProviders()
      .then(setProviders)
      .catch(() => {});
  }, []);

  async function load() {
    if (!selected) return;
    setLoading(true);
    setError('');
    setSummary(null);
    try {
      const data = await fetchSummary(selected);
      setSummary(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load summary');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Pre-Visit Summary</h3>

      <div className="flex gap-2">
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          className="flex-1 bg-[#0d1117] border border-[#30363d] focus:border-[#58a6ff] rounded-lg px-2 py-1.5 text-sm text-gray-200 outline-none"
        >
          <option value="">Select upcoming provider…</option>
          {providers.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name} — {String(p.properties?.clinic ?? '')}
            </option>
          ))}
        </select>
        <button
          onClick={load}
          disabled={!selected || loading}
          className="px-3 py-1.5 bg-[#1f6feb] hover:bg-[#388bfd] disabled:opacity-40 rounded-lg text-sm font-medium transition-colors"
        >
          {loading ? '…' : 'Generate'}
        </button>
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}

      {summary && (
        <div className="bg-[#0d1117] border border-[#30363d] rounded-lg p-3 animate-fade-in flex flex-col gap-2">
          <div className="flex justify-between text-xs text-gray-400">
            <span>
              <span className="text-white font-semibold">{String(summary.pet ?? '')}</span> → {String(summary.provider ?? '')}
            </span>
            <span>Last visit: {String(summary.last_visit_date ?? 'unknown')}</span>
          </div>

          {Array.isArray(summary.new_medications) && summary.new_medications.length > 0 && (
            <div>
              <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">New Medications</p>
              {(summary.new_medications as Record<string, unknown>[]).map((m, i) => (
                <p key={i} className="text-xs text-green-300">• {String(m.name ?? m)}</p>
              ))}
            </div>
          )}

          {Array.isArray(summary.new_vaccines) && summary.new_vaccines.length > 0 && (
            <div>
              <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Vaccines (not in your records)</p>
              {(summary.new_vaccines as Record<string, unknown>[]).map((v, i) => (
                <p key={i} className="text-xs text-cyan-300">• {String(v.name ?? v)}</p>
              ))}
            </div>
          )}

          {Array.isArray(summary.other_providers_seen) && summary.other_providers_seen.length > 0 && (
            <div>
              <p className="text-[10px] text-gray-500 uppercase tracking-wider mb-1">Other Providers Seen</p>
              {(summary.other_providers_seen as string[]).map((p, i) => (
                <p key={i} className="text-xs text-violet-300">• {p}</p>
              ))}
            </div>
          )}

          {summary.summary != null && (
            <div className="border-t border-[#30363d] pt-2 mt-1">
              <p className="text-xs text-gray-300 leading-relaxed whitespace-pre-line">{String(summary.summary as string)}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
