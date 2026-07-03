import axios from 'axios';
import type { CogneeStatus, GraphData, Insight, Reminder } from '../types';

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

export async function fetchPetSubgraph(petId: string): Promise<GraphData> {
  const { data } = await api.get(`/graph/pet/${petId}/subgraph`);
  return data;
}

export async function fetchCogneeStatus(): Promise<CogneeStatus> {
  const { data } = await api.get('/graph/cognee/status');
  return data;
}

export async function querySymptom(
  text: string,
  history: { role: string; content: string }[] = [],
) {
  const { data } = await api.post('/query/symptom', { text, history });
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

export async function fetchReminders(): Promise<{ reminders: Reminder[]; count: number; overdue_count: number }> {
  const { data } = await api.get('/reminders');
  return data;
}

export async function dismissReminder(id: string) {
  await api.post(`/reminders/${id}/dismiss`);
}

export async function snoozeReminder(id: string, until: string) {
  await api.post(`/reminders/${id}/snooze`, { until });
}

export async function fetchInsights(): Promise<{ insights: Insight[]; count: number }> {
  const { data } = await api.get('/insights');
  return data;
}

export async function dismissInsight(id: string) {
  await api.post(`/insights/${id}/dismiss`);
}

export async function resetGraph() {
  await api.delete('/ingest/reset');
}

export async function fetchDocuments() {
  const { data } = await api.get('/ingest/documents');
  return data.documents;
}
