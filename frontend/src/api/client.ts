import axios from 'axios';

const api = axios.create({ baseURL: '/api' });

export async function fetchGraph() {
  const { data } = await api.get('/graph');
  return data;
}

export async function fetchNode(id: string) {
  const { data } = await api.get(`/graph/node/${id}`);
  return data;
}

export async function fetchProviders() {
  const { data } = await api.get('/graph/providers');
  return data.providers as { id: string; name: string; properties: Record<string, unknown> }[];
}

export async function querySymptom(text: string) {
  const { data } = await api.post('/query/symptom', { text });
  return data;
}

export async function fetchConflicts() {
  const { data } = await api.get('/conflicts');
  return data;
}

export async function fetchSummary(providerId: string) {
  const { data } = await api.get(`/summary/${providerId}`);
  return data;
}

export async function resetGraph() {
  await api.delete('/ingest/reset');
}

export async function fetchDocuments() {
  const { data } = await api.get('/ingest/documents');
  return data.documents;
}

/** Upload a file and yield SSE events. Returns a cleanup function. */
export function uploadDocument(
  file: File,
  onEvent: (e: { stage: string; message: string; pct: number; doc_id?: string }) => void,
): () => void {
  const form = new FormData();
  form.append('file', file);

  const controller = new AbortController();

  fetch('/api/ingest/upload', { method: 'POST', body: form, signal: controller.signal })
    .then((res) => _consumeSSE(res, onEvent))
    .catch((e) => {
      if (e.name !== 'AbortError') console.error('upload error', e);
    });

  return () => controller.abort();
}

/** Stream seed document ingestion. Returns cleanup. */
export function seedDocuments(
  onEvent: (e: { stage: string; message: string; pct: number; file?: string; file_index?: number }) => void,
): () => void {
  const controller = new AbortController();

  fetch('/api/ingest/seed', { signal: controller.signal })
    .then((res) => _consumeSSE(res, onEvent))
    .catch((e) => {
      if (e.name !== 'AbortError') console.error('seed error', e);
    });

  return () => controller.abort();
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function _consumeSSE(res: Response, cb: (e: any) => void) {
  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const parts = buf.split('\n\n');
    buf = parts.pop() ?? '';
    for (const part of parts) {
      const dataLine = part.split('\n').find((l) => l.startsWith('data:'));
      if (dataLine) {
        try {
          cb(JSON.parse(dataLine.slice(5).trim()));
        } catch {}
      }
    }
  }
}
