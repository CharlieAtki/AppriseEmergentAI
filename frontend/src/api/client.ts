/**
 * Shared Axios transport layer for all Orval-generated hooks.
 *
 * Three jobs:
 *  1. Base URL — reads NEXT_PUBLIC_API_URL so all hooks point at the right backend.
 *  2. Auth — setAuthTokenGetter (called by AxiosAuthSync in providers.tsx) registers
 *             Clerk's getToken here; the request interceptor below attaches it as a
 *             Bearer token, so every generated hook is automatically authenticated.
 *  3. Runtime validation — inject-zod-validation.mjs passes a Zod schema as the third
 *                          arg; we parse res.data so malformed responses throw at the
 *                          HTTP boundary, not deep in the UI.
 *
 * httpClient: 'axios' in orval.config.ts means Orval calls customInstance with an
 * AxiosRequestConfig object as the first arg (not a fetch-style URL + RequestInit pair).
 */
import Axios, { type AxiosRequestConfig } from 'axios'
import type { ZodType } from 'zod'

export const AXIOS_INSTANCE = Axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000',
})

type AuthTokenGetter = () => Promise<string | null>

let authTokenGetter: AuthTokenGetter | null = null

export function setAuthTokenGetter(getter: AuthTokenGetter | null): void {
  authTokenGetter = getter
}

AXIOS_INSTANCE.interceptors.request.use(async (config) => {
  try {
    const token = await authTokenGetter?.()
    if (token) config.headers.Authorization = `Bearer ${token}`
  } catch {
    // no-op: unauthenticated requests proceed without the header
  }
  return config
})

export const customInstance = async <T>(
  config: AxiosRequestConfig,
  _options?: unknown,
  schema?: ZodType,
): Promise<T> => {
  const res = await AXIOS_INSTANCE.request<T>(config)
  const data = schema ? schema.parse(res.data) : res.data
  return data as T
}
