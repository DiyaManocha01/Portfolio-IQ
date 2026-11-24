import { api } from './api';
import type { AssistantAnswer } from '../types/api';

export async function askAssistant(question: string): Promise<AssistantAnswer> {
  const res = await api.post<AssistantAnswer>('/assistant/ask', { question });
  return res.data;
}
