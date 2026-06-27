import Axios, { type AxiosRequestConfig } from 'axios'

export const AXIOS_INSTANCE = Axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000',
})

// Orval 8 calls mutators as (url, fetchOptions) where fetchOptions uses
// fetch-style `body` (not Axios-style `data`). Bridge here so all generated
// hooks share one HTTP client and one auth injection point.
export const customInstance = <T>(url: string, options?: RequestInit): Promise<T> => {
  const config: AxiosRequestConfig = { url }
  if (options?.method !== undefined) config.method = options.method
  if (options?.headers !== undefined) config.headers = options.headers as Record<string, string>
  if (options?.body !== undefined) config.data = options.body
  if (options?.signal !== undefined) config.signal = options.signal as AbortSignal

  return AXIOS_INSTANCE.request<T>(config).then((res) => res.data as T)
}

// Clerk auth header injection — uncomment when auth is added:
// AXIOS_INSTANCE.interceptors.request.use(async (config) => {
//   const token = await clerkClient.getToken()
//   config.headers.Authorization = `Bearer ${token}`
//   return config
// })
