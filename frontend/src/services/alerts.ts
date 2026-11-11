import { api } from './api';
import type { AlertEventOut, AlertRuleCreate, AlertRuleOut, AlertRuleUpdate } from '../types/api';

export async function createRule(payload: AlertRuleCreate): Promise<AlertRuleOut> {
  const res = await api.post<AlertRuleOut>('/alerts/rules', payload);
  return res.data;
}

export async function listRules(): Promise<AlertRuleOut[]> {
  const res = await api.get<AlertRuleOut[]>('/alerts/rules');
  return res.data;
}

export async function updateRule(id: number, payload: AlertRuleUpdate): Promise<AlertRuleOut> {
  const res = await api.patch<AlertRuleOut>(`/alerts/rules/${id}`, payload);
  return res.data;
}

export async function deleteRule(id: number): Promise<void> {
  await api.delete(`/alerts/rules/${id}`);
}

export async function evaluateRules(): Promise<AlertEventOut[]> {
  const res = await api.post<AlertEventOut[]>('/alerts/evaluate');
  return res.data;
}

export async function listEvents(unreadOnly = false): Promise<AlertEventOut[]> {
  const res = await api.get<AlertEventOut[]>('/alerts/events', { params: { unread_only: unreadOnly } });
  return res.data;
}

export async function markEventRead(id: number): Promise<AlertEventOut> {
  const res = await api.post<AlertEventOut>(`/alerts/events/${id}/read`);
  return res.data;
}
