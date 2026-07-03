import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { querySymptom } from '../api/client';
import type { QueryResult, Citation, RelevanceLevel, TraceOp } from '../types';

interface Props {
  onResult: (result: QueryResult) => void;
  onShowMap: (result: QueryResult) => void;
  hasRecords: boolean;
}

interface ChatEntry {
  role: 'user' | 'assistant';
  text: string;          // plain text (no citation chips) — used as history sent to API
  result?: QueryResult;  // assistant only
}

const STARTERS = [
  "she's rubbing her ears again",
  'what medications is Bella on?',
  'has Charlie had any vaccines?',
  'Bella vomited twice today',
];

export default function AskPanel({ onResult, onShowMap, hasRecords }: Props) {
  const [chat, setChat] = useState<ChatEntry[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [openDrawer, setOpenDrawer] = useState<string | null>(null); // `${i}:why` | `${i}:how`
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chat, loading, openDrawer]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    setInput('');
    setError('');

    const userEntry: ChatEntry = { role: 'user', text: trimmed };
    setChat((prev) => [...prev, userEntry]);

    setLoading(true);
    try {
      const history = [...chat, userEntry].map((e) => ({
        role: e.role,
        content: e.text.replace(/\[[^\]\n]{2,60}\]/g, '').replace(/\s+/g, ' ').trim(),
      }));

      const result: QueryResult = await querySymptom(trimmed, history.slice(-8));
      setChat((prev) => [...prev, { role: 'assistant', text: result.summary, result }]);
      onResult(result);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Something went wrong — please try again.');
      setChat((prev) => prev.slice(0, -1));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="h-full flex flex-col max-w-2xl mx-auto w-full px-4">
      {/* Chat history */}
      <div className="flex-1 overflow-y-auto flex flex-col gap-4 py-6 min-h-0">
        {chat.length === 0 && (
          <div className="flex flex-col items-center justify-center flex-1 gap-4 text-center">
            <span className="text-4xl">🐾</span>
            <div>
              <h2 className="text-lg font-semibold text-white">Ask about your pet's health</h2>
              <p className="text-xs text-gray-500 mt-1">
                {hasRecords
                  ? 'Describe a symptom or ask anything about past visits, medicines, or vaccines.'
                  : 'Load your records first (Records tab), then ask anything about them.'}
              </p>
            </div>
            {hasRecords && (
              <div className="flex flex-col gap-2 w-full max-w-sm">
                {STARTERS.map((q) => (
                  <button
                    key={q}
                    onClick={() => send(q)}
                    className="text-left text-xs text-gray-400 hover:text-white bg-[#161b22] hover:bg-[#1f2937] border border-[#30363d] hover:border-[#1f6feb]/50 px-4 py-2.5 rounded-xl transition-colors"
                  >
                    {q}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}

        {chat.map((entry, i) => (
          <div key={i} className={`flex flex-col gap-1.5 ${entry.role === 'user' ? 'items-end' : 'items-start'}`}>
            {entry.role === 'user' ? (
              <div className="bg-[#1f6feb]/20 border border-[#1f6feb]/30 rounded-2xl rounded-tr-md px-4 py-2.5 max-w-[85%]">
                <p className="text-sm text-gray-200">{entry.text}</p>
              </div>
            ) : (
              <div className="flex flex-col gap-2 w-full">
                {/* Relevance chip — honest about whether history was used */}
                {entry.result && <RelevanceChip level={entry.result.relevance?.level} />}

                {/* Answer bubble */}
                <div className="bg-[#161b22] border border-[#30363d] rounded-2xl rounded-tl-md px-4 py-3">
                  <p className="text-sm text-gray-200 leading-relaxed">{renderWithCitations(entry.text)}</p>
                </div>

                {/* Secondary actions — progressive disclosure */}
                {entry.result && (
                  <div className="flex flex-wrap items-center gap-3 px-1">
                    {entry.result.citations.length > 0 && (
                      <DrawerToggle
                        label="Why this answer"
                        open={openDrawer === `${i}:why`}
                        onClick={() => setOpenDrawer(openDrawer === `${i}:why` ? null : `${i}:why`)}
                      />
                    )}
                    {entry.result.nodes.length > 0 && (
                      <button
                        onClick={() => onShowMap(entry.result!)}
                        className="text-[11px] text-gray-500 hover:text-[#58a6ff] transition-colors"
                      >
                        See it on the health map →
                      </button>
                    )}
                    <DrawerToggle
                      label="How Cognee found this"
                      open={openDrawer === `${i}:how`}
                      onClick={() => setOpenDrawer(openDrawer === `${i}:how` ? null : `${i}:how`)}
                    />
                  </div>
                )}

                {openDrawer === `${i}:why` && entry.result && <WhyDrawer result={entry.result} />}
                {openDrawer === `${i}:how` && entry.result && <HowDrawer result={entry.result} />}

                {/* Follow-up suggestion chips */}
                {entry.result && entry.result.suggestions.length > 0 && i === chat.length - 1 && (
                  <div className="flex flex-wrap gap-1.5 px-1 pt-1">
                    {entry.result.suggestions.map((s, si) => (
                      <button
                        key={si}
                        onClick={() => send(s)}
                        disabled={loading}
                        className="text-[11px] text-[#58a6ff] hover:text-white bg-[#1f6feb]/10 hover:bg-[#1f6feb]/25 border border-[#1f6feb]/20 hover:border-[#1f6feb]/50 px-3 py-1.5 rounded-full transition-colors disabled:opacity-40"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex items-start">
            <div className="bg-[#161b22] border border-[#30363d] rounded-2xl rounded-tl-md px-4 py-3 flex items-center gap-2">
              <div className="flex gap-1">
                {[0, 1, 2].map((i) => (
                  <div
                    key={i}
                    className="w-1.5 h-1.5 rounded-full bg-[#58a6ff] animate-bounce"
                    style={{ animationDelay: `${i * 150}ms` }}
                  />
                ))}
              </div>
              <span className="text-[11px] text-gray-500">Checking the records…</span>
            </div>
          </div>
        )}

        {error && (
          <div className="text-xs text-red-400 bg-red-900/20 border border-red-800 rounded-lg px-3 py-2">
            {error}
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      {/* Input — the one primary action */}
      <div className="shrink-0 pb-5 pt-2">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send(input)}
            placeholder={chat.length > 0 ? 'Ask a follow-up…' : "Describe a symptom or ask about your pet's history…"}
            disabled={loading}
            autoFocus
            className="flex-1 bg-[#161b22] border border-[#30363d] focus:border-[#58a6ff] rounded-xl px-4 py-3 text-sm text-gray-100 placeholder-gray-600 outline-none transition-colors disabled:opacity-50"
          />
          <button
            onClick={() => send(input)}
            disabled={loading || !input.trim()}
            className="px-5 py-3 bg-[#1f6feb] hover:bg-[#388bfd] disabled:opacity-40 rounded-xl text-sm font-semibold transition-colors"
          >
            Ask
          </button>
        </div>
        {chat.length > 0 && (
          <button
            onClick={() => { setChat([]); setError(''); setOpenDrawer(null); }}
            className="text-[10px] text-gray-600 hover:text-gray-400 mt-2 transition-colors"
          >
            Start a new conversation
          </button>
        )}
      </div>
    </div>
  );
}

// ── Sub-components ────────────────────────────────────────────────────────────

function RelevanceChip({ level }: { level?: RelevanceLevel }) {
  if (!level) return null;
  if (level === 'strong' || level === 'moderate') {
    return (
      <span className="text-[10px] text-emerald-300 bg-emerald-900/30 border border-emerald-800/50 px-2 py-0.5 rounded-full self-start">
        {level === 'strong' ? 'Connected to past records' : 'Possibly related to past records'}
      </span>
    );
  }
  if (level === 'unavailable') {
    return (
      <span className="text-[10px] text-gray-400 bg-[#161b22] border border-[#30363d] px-2 py-0.5 rounded-full self-start">
        Records are still being prepared — general guidance only
      </span>
    );
  }
  return (
    <span className="text-[10px] text-gray-400 bg-[#161b22] border border-[#30363d] px-2 py-0.5 rounded-full self-start">
      No closely related history — general guidance
    </span>
  );
}

function DrawerToggle({ label, open, onClick }: { label: string; open: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} className="text-[11px] text-gray-500 hover:text-[#58a6ff] transition-colors">
      {label} {open ? '▴' : '▾'}
    </button>
  );
}

function WhyDrawer({ result }: { result: QueryResult }) {
  return (
    <div className="bg-[#0d1117] border border-[#21262d] rounded-xl p-3 animate-fade-in">
      {result.relevance?.explanation && (
        <p className="text-[11px] text-gray-400 mb-2 leading-relaxed">{result.relevance.explanation}</p>
      )}
      <p className="text-[10px] text-gray-600 uppercase tracking-wider mb-1.5">From these records</p>
      <div className="flex flex-col gap-1">
        {result.citations.map((c: Citation & { provider?: string }, ci: number) => (
          <div key={ci} className="flex items-center gap-2 text-[11px]">
            <span className="w-1.5 h-1.5 rounded-full shrink-0" style={{ background: typeColor(c.type) }} />
            <span className="text-gray-300">{c.entity}</span>
            {c.date && <span className="text-gray-600">{c.date}</span>}
            {c.provider && <span className="text-gray-600">· {c.provider}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}

function HowDrawer({ result }: { result: QueryResult }) {
  const trace = result.cognee_trace;
  if (!trace) return null;
  return (
    <div className="bg-[#0d1117] border border-[#21262d] rounded-xl p-3 font-mono text-[10px] animate-fade-in flex flex-col gap-2 overflow-x-auto">
      <p className="text-gray-500">
        semantic index: <span className="text-gray-300">{trace.semantic_status?.state ?? 'unknown'}</span>
        {' · '}docs indexed: <span className="text-gray-300">{trace.semantic_status?.docs_indexed ?? 0}</span>
      </p>
      {result.relevance && (
        <p className="text-gray-500">
          relevance: <span className="text-gray-300">{result.relevance.level}</span>
          {result.relevance.best_score != null && (
            <>
              {' '}(best distance <span className="text-gray-300">{result.relevance.best_score}</span>, strong ≤{' '}
              {result.relevance.thresholds.strong}, weak &gt; {result.relevance.thresholds.weak})
            </>
          )}
        </p>
      )}
      {(trace.operations ?? []).map((op: TraceOp, oi: number) => (
        <div key={oi} className="border-t border-[#21262d] pt-2">
          <p className="text-[#58a6ff]">
            {op.op} <span className="text-gray-600">— {op.engine}</span>
          </p>
          {op.error && <p className="text-red-400 mt-0.5">error: {op.error}</p>}
          {op.cypher && <p className="text-gray-500 mt-0.5 whitespace-pre-wrap">{op.cypher}</p>}
          {op.hop1_count != null && (
            <p className="text-gray-500 mt-0.5">1-hop: {op.hop1_count} · 2-hop: {op.hop2_count}</p>
          )}
          {op.answer && <p className="text-gray-400 mt-0.5">→ {op.answer}</p>}
          {(op.results ?? []).map((r, ri) => (
            <p key={ri} className="text-gray-500 mt-0.5 truncate">
              [{r.score}] {r.document ?? '?'} — {r.snippet}
            </p>
          ))}
        </div>
      ))}
    </div>
  );
}

function renderWithCitations(text: string): ReactNode {
  const parts = text.split(/(\[[^\]\n]{2,60}\])/g);
  return parts.map((part, i) => {
    if (/^\[.{2,60}\]$/.test(part)) {
      return (
        <span
          key={i}
          className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] bg-[#1f6feb]/20 text-[#79b8ff] border border-[#1f6feb]/30 mx-0.5 align-middle whitespace-nowrap"
        >
          {part.slice(1, -1)}
        </span>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

function typeColor(type: string): string {
  const map: Record<string, string> = {
    symptom: '#fb7185', diagnosis: '#f97316', medication: '#4ade80',
    vaccine: '#22d3ee', visit: '#34d399', provider: '#a78bfa',
  };
  return map[type] ?? '#6b7280';
}
