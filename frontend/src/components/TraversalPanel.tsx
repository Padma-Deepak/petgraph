import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { querySymptom } from '../api/client';
import type { QueryResult, Citation } from '../types';

interface Props {
  onTraversalResult: (result: QueryResult) => void;
}

interface ChatEntry {
  role: 'user' | 'assistant';
  text: string;          // plain text (no citation chips) — used as history sent to API
  result?: QueryResult;  // assistant only
}

const STARTERS = [
  "she's rubbing her ears again",
  "what medications is Bella on?",
  "has Charlie had any vaccines?",
  "show me her full diagnosis history",
];

export default function TraversalPanel({ onTraversalResult }: Props) {
  const [chat, setChat] = useState<ChatEntry[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [chat, loading]);

  async function send(text: string) {
    const trimmed = text.trim();
    if (!trimmed || loading) return;

    setInput('');
    setError('');

    const userEntry: ChatEntry = { role: 'user', text: trimmed };
    setChat((prev) => [...prev, userEntry]);

    setLoading(true);
    try {
      // Build history from prior chat (strip inline citation chips from assistant text)
      const history = [...chat, userEntry].map((e) => ({
        role: e.role,
        content: e.text.replace(/\[[^\]\n]{2,60}\]/g, '').replace(/\s+/g, ' ').trim(),
      }));

      const result: QueryResult = await querySymptom(trimmed, history.slice(-8));

      const assistantEntry: ChatEntry = {
        role: 'assistant',
        text: result.summary,
        result,
      };
      setChat((prev) => [...prev, assistantEntry]);
      onTraversalResult(result);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Query failed');
      setChat((prev) => prev.slice(0, -1)); // remove the user bubble on error
    } finally {
      setLoading(false);
    }
  }

  function clearChat() {
    setChat([]);
    setError('');
  }

  return (
    <div className="flex flex-col h-full gap-0">
      {/* Header */}
      <div className="flex items-center justify-between mb-2 shrink-0">
        <span className="text-[10px] text-gray-500 uppercase tracking-wider font-semibold">Graph Query</span>
        {chat.length > 0 && (
          <button
            onClick={clearChat}
            className="text-[9px] text-gray-600 hover:text-gray-400 transition-colors"
          >
            clear
          </button>
        )}
      </div>

      {/* Chat history */}
      <div className="flex-1 overflow-y-auto flex flex-col gap-3 pr-1 min-h-0">
        {chat.length === 0 && (
          <div className="flex flex-col gap-2 pt-2">
            <p className="text-[10px] text-gray-600 text-center mb-1">Ask about your pet's health history</p>
            <div className="flex flex-col gap-1">
              {STARTERS.map((q) => (
                <button
                  key={q}
                  onClick={() => send(q)}
                  className="text-left text-[11px] text-gray-500 hover:text-[#58a6ff] bg-[#0d1117] hover:bg-[#1f2937] border border-[#21262d] hover:border-[#1f6feb]/40 px-3 py-2 rounded-lg transition-colors"
                >
                  {q}
                </button>
              ))}
            </div>
          </div>
        )}

        {chat.map((entry, i) => (
          <div key={i} className={`flex flex-col gap-1 ${entry.role === 'user' ? 'items-end' : 'items-start'}`}>
            {entry.role === 'user' ? (
              <div className="bg-[#1f6feb]/20 border border-[#1f6feb]/30 rounded-xl rounded-tr-sm px-3 py-2 max-w-[90%]">
                <p className="text-sm text-gray-200">{entry.text}</p>
              </div>
            ) : (
              <div className="flex flex-col gap-2 w-full">
                {/* Answer bubble */}
                <div className="bg-[#0d1117] border border-[#30363d] rounded-xl rounded-tl-sm px-3 py-2.5">
                  {entry.result && (
                    <div className="flex gap-2 text-[9px] text-gray-600 mb-2 font-mono">
                      <span>{entry.result.anchor_nodes.length} anchors</span>
                      <span>→</span>
                      <span>{entry.result.traversal_path.length} hops</span>
                    </div>
                  )}
                  <p className="text-sm text-gray-200 leading-relaxed">
                    {renderWithCitations(entry.text)}
                  </p>
                </div>

                {/* Citations strip */}
                {entry.result && entry.result.citations.length > 0 && (
                  <div className="flex flex-wrap gap-1 px-1">
                    {entry.result.citations.map((c: Citation, ci: number) => (
                      <span
                        key={ci}
                        className="inline-flex items-center gap-1 text-[9px] px-1.5 py-0.5 rounded font-mono"
                        style={{ background: typeColor(c.type) + '22', color: typeColor(c.type) }}
                      >
                        <span className="uppercase opacity-70">{c.type[0]}</span>
                        <span>{c.entity}</span>
                        {c.date && <span className="opacity-50">· {c.date}</span>}
                      </span>
                    ))}
                  </div>
                )}

                {/* Follow-up suggestion chips */}
                {entry.result && entry.result.suggestions.length > 0 && (
                  <div className="flex flex-col gap-1 px-1">
                    <span className="text-[9px] text-gray-600">Follow up:</span>
                    <div className="flex flex-col gap-1">
                      {entry.result.suggestions.map((s, si) => (
                        <button
                          key={si}
                          onClick={() => send(s)}
                          disabled={loading}
                          className="text-left text-[11px] text-[#58a6ff] hover:text-white bg-[#1f6feb]/10 hover:bg-[#1f6feb]/25 border border-[#1f6feb]/20 hover:border-[#1f6feb]/50 px-2.5 py-1.5 rounded-lg transition-colors disabled:opacity-40"
                        >
                          {s}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}

        {loading && (
          <div className="flex items-start gap-2">
            <div className="bg-[#0d1117] border border-[#30363d] rounded-xl rounded-tl-sm px-3 py-2.5 flex items-center gap-2">
              <div className="flex gap-1">
                {[0, 1, 2].map((i) => (
                  <div
                    key={i}
                    className="w-1.5 h-1.5 rounded-full bg-[#58a6ff] animate-bounce"
                    style={{ animationDelay: `${i * 150}ms` }}
                  />
                ))}
              </div>
              <span className="text-[11px] text-gray-500">Searching graph…</span>
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

      {/* Input */}
      <div className="shrink-0 pt-2 border-t border-[#21262d] mt-2">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && send(input)}
            placeholder={chat.length > 0 ? 'Ask a follow-up…' : 'Describe a symptom or ask about history…'}
            disabled={loading}
            className="flex-1 bg-[#0d1117] border border-[#30363d] focus:border-[#58a6ff] rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-600 outline-none transition-colors disabled:opacity-50"
          />
          <button
            onClick={() => send(input)}
            disabled={loading || !input.trim()}
            className="px-3 py-2 bg-[#1f6feb] hover:bg-[#388bfd] disabled:opacity-40 rounded-lg text-sm font-medium transition-colors"
          >
            →
          </button>
        </div>
      </div>
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
          className="inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-mono bg-[#1f6feb]/20 text-[#58a6ff] border border-[#1f6feb]/30 mx-0.5 align-middle whitespace-nowrap"
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
