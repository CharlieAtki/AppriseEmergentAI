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

  const res = await AXIOS_INSTANCE.request<T>(config)
  return res.data as T
}
