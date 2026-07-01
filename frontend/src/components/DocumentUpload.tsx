import { useRef, useState } from 'react';
import type { IngestionEvent } from '../types';

interface Props {
  onGraphUpdate: () => void;
}

interface FileProgress {
  filename: string;
  message: string;
  pct: number;
  done: boolean;
  error: boolean;
}

export default function DocumentUpload({ onGraphUpdate }: Props) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [seeding, setSeeding] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [progresses, setProgresses] = useState<FileProgress[]>([]);
  const [seedDone, setSeedDone] = useState(false);
  const [seedError, setSeedError] = useState('');

  function updateProgress(filename: string, event: IngestionEvent) {
    setProgresses((prev) => {
      const idx = prev.findIndex((p) => p.filename === filename);
      const updated: FileProgress = {
        filename,
        message: event.message,
        pct: event.pct,
        done: event.pct >= 100 || event.stage === 'done' || event.stage === 'all_done',
        error: event.stage === 'error',
      };
      if (idx === -1) return [...prev, updated];
      const next = [...prev];
      next[idx] = updated;
      return next;
    });
  }

  async function handleSeed() {
    setSeeding(true);
    setSeedError('');
    setSeedDone(false);
    setProgresses([{ filename: 'seed-data', message: 'Loading…', pct: 30, done: false, error: false }]);

    try {
      const r = await fetch('/api/ingest/seed');
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const data = await r.json();
      setProgresses([{
        filename: 'seed-data',
        message: `${data.node_count} nodes · ${data.edge_count} edges`,
        pct: 100,
        done: true,
        error: false,
      }]);
      setSeedDone(true);
      onGraphUpdate();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : 'Unknown error';
      setSeedError(msg);
      setProgresses([{ filename: 'seed-data', message: msg, pct: 0, done: false, error: true }]);
    } finally {
      setSeeding(false);
    }
  }

  function handleUpload(files: FileList) {
    setUploading(true);
    let pending = files.length;

    for (const file of Array.from(files)) {
      updateProgress(file.name, { stage: 'queued', message: 'Queued…', pct: 5 });

      const form = new FormData();
      form.append('file', file);

      const xhr = new XMLHttpRequest();
      xhr.open('POST', '/api/ingest/upload');
      let pos = 0;

      xhr.onprogress = () => {
        const chunk = xhr.responseText.slice(pos);
        pos = xhr.responseText.length;
        for (const part of chunk.split('\n\n').filter(Boolean)) {
          const dataLine = part.split('\n').find((l) => l.startsWith('data:'));
          if (!dataLine) continue;
          try {
            const ev: IngestionEvent = JSON.parse(dataLine.slice(5).trim());
            updateProgress(file.name, ev);
            if (ev.pct >= 100 || ev.stage === 'done') {
              pending -= 1;
              if (pending === 0) { setUploading(false); onGraphUpdate(); }
            }
          } catch { /* skip malformed */ }
        }
      };

      xhr.onload = () => {
        // flush any remaining buffer on stream close
        xhr.onprogress?.({ } as ProgressEvent);
        if (pending > 0) { pending = 0; setUploading(false); onGraphUpdate(); }
      };

      xhr.onerror = () => {
        updateProgress(file.name, { stage: 'error', message: 'Upload failed', pct: 0 });
        pending -= 1;
        if (pending === 0) setUploading(false);
      };

      xhr.send(form);
    }
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    if (e.dataTransfer.files.length) handleUpload(e.dataTransfer.files);
  }

  return (
    <div className="flex flex-col gap-3">
      <button
        onClick={handleSeed}
        disabled={seeding}
        className="w-full py-2 px-3 rounded-lg bg-[#1f6feb] hover:bg-[#388bfd] disabled:opacity-50 text-sm font-semibold transition-colors flex items-center justify-center gap-2"
      >
        {seeding ? (
          <>
            <span className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin" />
            Loading seed data…
          </>
        ) : seedDone ? (
          '✓ Seed data loaded'
        ) : (
          '🚀 Load Seed Data'
        )}
      </button>

      {seedError && <p className="text-xs text-red-400">{seedError}</p>}

      <div
        onDrop={onDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => fileRef.current?.click()}
        className="border border-dashed border-[#30363d] hover:border-[#58a6ff] rounded-lg p-4 text-center cursor-pointer text-xs text-gray-500 hover:text-gray-300 transition-colors"
      >
        Drop a .txt document or click to upload
        <input
          ref={fileRef}
          type="file"
          accept=".txt"
          multiple
          className="hidden"
          onChange={(e) => e.target.files && handleUpload(e.target.files)}
        />
      </div>

      {progresses.length > 0 && (
        <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto pr-1">
          {progresses.map((p) => (
            <div key={p.filename} className="bg-[#0d1117] rounded p-2">
              <div className="flex justify-between text-[10px] mb-1">
                <span className="text-gray-300 truncate max-w-[70%]">{p.filename}</span>
                <span className={p.error ? 'text-red-400' : p.done ? 'text-green-400' : 'text-[#58a6ff]'}>
                  {p.done ? '✓' : p.error ? '✗' : `${p.pct}%`}
                </span>
              </div>
              <div className="h-1 bg-[#21262d] rounded overflow-hidden">
                <div
                  className={`h-full rounded transition-all duration-500 ${
                    p.error ? 'bg-red-500' : p.done ? 'bg-green-500' : 'bg-[#58a6ff]'
                  }`}
                  style={{ width: `${p.pct}%` }}
                />
              </div>
              <p className="text-[9px] text-gray-500 mt-0.5 truncate">{p.message}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

