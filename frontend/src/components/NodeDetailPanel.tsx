import { useEffect, useState } from 'react';
import { fetchNode } from '../api/client';
import type { GraphNode } from '../types';

const TYPE_ICONS: Record<string, string> = {
  pet: '🐾', owner: '👤', provider: '🏥', visit: '📋',
  symptom: '⚡', diagnosis: '🔬', medication: '💊', vaccine: '💉',
};

interface Props {
  nodeId: string | null;
  onClose: () => void;
}

export default function NodeDetailPanel({ nodeId, onClose }: Props) {
  const [node, setNode] = useState<(GraphNode & { neighbors?: GraphNode[]; source_documents?: { filename: string; content: string }[] }) | null>(null);

  useEffect(() => {
    if (!nodeId) { setNode(null); return; }
    fetchNode(nodeId).then(setNode).catch(() => setNode(null));
  }, [nodeId]);

  if (!nodeId || !node) return null;

  const aliases = (node.properties?.aliases as string[]) ?? [];
  const docs = node.source_documents ?? [];

  return (
    <div className="fixed right-4 top-4 bottom-4 w-80 bg-[#161b22] border border-[#30363d] rounded-xl shadow-2xl z-50 flex flex-col overflow-hidden animate-fade-in">
      <div className="flex items-center justify-between p-4 border-b border-[#30363d]">
        <div className="flex items-center gap-2">
          <span className="text-xl">{TYPE_ICONS[node.type] ?? '●'}</span>
          <div>
            <h2 className="text-sm font-semibold text-white">{node.name}</h2>
            <span className="text-[10px] text-gray-500 font-mono">{node.type}</span>
          </div>
        </div>
        <button onClick={onClose} className="text-gray-500 hover:text-white text-lg">×</button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 flex flex-col gap-4">
        {/* Properties */}
        <div>
          <h4 className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">Details</h4>
          <div className="flex flex-col gap-1">
            {Object.entries(node.properties ?? {}).map(([k, v]) => {
              if (k === 'aliases' || v === null || v === undefined || v === '') return null;
              return (
                <div key={k} className="flex justify-between text-xs">
                  <span className="text-gray-500">{k.replace(/_/g, ' ')}</span>
                  <span className="text-gray-200 text-right max-w-[60%]">{String(v)}</span>
                </div>
              );
            })}
          </div>
        </div>

        {/* Entity resolution — show aliases for pet nodes */}
        {node.type === 'pet' && aliases.length > 0 && (
          <div>
            <h4 className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">
              Also appears in records as
            </h4>
            <div className="flex flex-col gap-1">
              {aliases.map((a, i) => (
                <div key={i} className="flex items-center gap-1.5 text-xs">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#f5a623]" />
                  <span className="text-gray-300 font-mono">{a}</span>
                </div>
              ))}
            </div>
            <p className="text-[9px] text-gray-600 mt-2">
              Different clinics used different names — they've been matched to the same pet automatically.
            </p>
          </div>
        )}

        {/* Source documents */}
        {docs.length > 0 && (
          <div>
            <h4 className="text-[10px] text-gray-500 uppercase tracking-wider mb-2">From these records</h4>
            {docs.map((d) => (
              <div key={d.filename} className="bg-[#0d1117] rounded p-2 mb-1.5">
                <p className="text-[10px] text-[#58a6ff] font-mono mb-1">{d.filename}</p>
                <p className="text-[9px] text-gray-500 line-clamp-3">{d.content.slice(0, 200)}…</p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
