import { api } from './api';
import type { AuthResponse, User } from '../types/api';

export async function login(email: string, password: string): Promise<AuthResponse> {
  const res = await api.post<AuthResponse>('/auth/login', { email, password });
  return res.data;
}

export async function register(email: string, password: string, full_name: string): Promise<AuthResponse> {
  const res = await api.post<AuthResponse>('/auth/register', { email, password, full_name });
  return res.data;
}

export async function fetchMe(): Promise<User> {
  const res = await api.get<User>('/auth/me');
  return res.data;
}
