/**
 * Shared Axios transport layer for all Orval-generated hooks.
 *
 * Three jobs:
 *  1. Base URL — reads NEXT_PUBLIC_API_URL so all hooks point at the right backend.
 *  2. Auth — AxiosAuthSync (providers.tsx) attaches a Clerk Bearer token interceptor
 *             to AXIOS_INSTANCE, so every generated hook is automatically authenticated.
 *  3. Response shape — Orval's `mutator` config expects { data, status, headers };
 *                      customInstance returns that shape so runtime and generated types agree.
 */
import Axios, { type AxiosRequestConfig } from 'axios'

export const AXIOS_INSTANCE = Axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000',
})

export const customInstance = async <T>(url: string, options?: RequestInit): Promise<T> => {
  const config: AxiosRequestConfig = { url }
  if (options?.method !== undefined) config.method = options.method
  if (options?.headers !== undefined) config.headers = options.headers as Record<string, string>
  if (options?.body !== undefined) config.data = options.body
  if (options?.signal !== undefined) config.signal = options.signal as AbortSignal

  const res = await AXIOS_INSTANCE.request(config)
  return { data: res.data, status: res.status, headers: res.headers } as T
}
