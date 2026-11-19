import type { Job, JobListItem, SurveyInput, SurveySample } from './types'

export interface AuthUser { username: string; role: 'admin' | 'user' }
export interface UserRow extends AuthUser { created_at: string | null; builtin: boolean }

const TOKEN_KEY = 'vandrishti-token'
let token = ''
try {
  token = localStorage.getItem(TOKEN_KEY) ?? ''
} catch {
  /* storage blocked: stay signed in for this page load only */
}

export function setToken(value: string) {
  token = value
  try {
    if (value) localStorage.setItem(TOKEN_KEY, value)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* storage blocked */
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const res = await fetch(path, { ...init, headers })
  if (res.status === 401 && token && !path.startsWith('/api/auth/')) {
    setToken('')
    window.dispatchEvent(new Event('vandrishti-signed-out'))
  }
  if (!res.ok) {
    let detail = res.statusText
    try {
      detail = (await res.json()).detail ?? detail
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail)
  }
  return res.json() as Promise<T>
}

const json = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: body === undefined ? undefined : JSON.stringify(body),
})

export const api = {
  authStatus: () => request<{ enabled: boolean; user: AuthUser | null }>('/api/auth/status'),
  login: (username: string, password: string) =>
    request<{ token: string; user: AuthUser }>('/api/auth/login', json('POST', { username, password })),
  users: () => request<UserRow[]>('/api/auth/users'),
  addUser: (username: string, password: string, role: string) =>
    request<AuthUser>('/api/auth/users', json('POST', { username, password, role })),
  removeUser: (username: string) => request<unknown>(`/api/auth/users/${encodeURIComponent(username)}`, json('DELETE')),
  changePassword: (current: string, next: string) =>
    request<unknown>('/api/auth/password', json('POST', { current, new: next })),
  health: () => request<{ status: string; gee_project_configured: boolean }>('/api/health'),
  samples: () => request<{ filename: string; name: string }[]>('/api/samples'),
  jobs: () => request<JobListItem[]>('/api/jobs'),
  job: (id: string) => request<Job>(`/api/jobs/${id}`),
  createJob: (file: File, name: string, options: Record<string, number>) => {
    const form = new FormData()
    form.append('file', file)
    if (name) form.append('name', name)
    form.append('options', JSON.stringify(options))
    return request<{ id: string }>('/api/jobs', { method: 'POST', body: form })
  },
  surveySamples: () => request<SurveySample[]>('/api/samples/survey'),
  createSurveyJob: (boundary: File, files: Partial<Record<SurveyInput, File>>, name: string, options: Record<string, number>) => {
    const form = new FormData()
    form.append('boundary', boundary)
    for (const [k, f] of Object.entries(files)) if (f) form.append(k, f)
    if (name) form.append('name', name)
    form.append('options', JSON.stringify(options))
    return request<{ id: string }>('/api/jobs/survey', { method: 'POST', body: form })
  },
  createFromSurveySample: (id: string) =>
    request<{ id: string }>(`/api/jobs/from-survey-sample/${encodeURIComponent(id)}`, { method: 'POST' }),
  createFromSample: (filename: string) =>
    request<{ id: string }>(`/api/jobs/from-sample/${encodeURIComponent(filename)}`, { method: 'POST' }),
}

export const fileUrl = (jobId: string, file: string, download = false) => {
  const query = new URLSearchParams()
  if (download) query.set('download', 'true')
  if (token) query.set('token', token)  // images and download links cannot send the sign-in header
  const qs = query.toString()
  return `/api/jobs/${jobId}/files/${encodeURIComponent(file)}${qs ? `?${qs}` : ''}`
}
