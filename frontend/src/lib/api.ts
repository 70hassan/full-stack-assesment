import type { Heatmap, Place, Plan, TripRequest } from './types'

const BASE = import.meta.env.VITE_API_BASE ?? ''

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await fetch(BASE + path, init)
  } catch (error) {
    if ((error as Error).name === 'AbortError') throw error
    throw new Error('Could not reach the server. Check your connection and try again.')
  }
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    /* non-JSON error page */
  }
  if (!response.ok) {
    const message = (body as { error?: string } | null)?.error
    throw new Error(message || `The server returned an error (${response.status}).`)
  }
  return body as T
}

const post = <T,>(path: string, body: unknown, signal?: AbortSignal) =>
  request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal,
  })

export const searchPlaces = (query: string, signal?: AbortSignal) =>
  request<{ results: Place[] }>(`/api/places?q=${encodeURIComponent(query)}`, { signal }).then((r) => r.results)

export const planTrip = (trip: TripRequest, signal?: AbortSignal) => post<Plan>('/api/trips/plan', trip, signal)

export const fetchHeatmap = (trip: TripRequest, signal?: AbortSignal) =>
  post<Heatmap>('/api/trips/heatmap', trip, signal)
