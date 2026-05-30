import Axios, { type AxiosRequestConfig } from 'axios'

export const AXIOS_INSTANCE = Axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000',
})

// Uncomment when Clerk auth is wired up:
// AXIOS_INSTANCE.interceptors.request.use(async (config) => {
//   const token = await clerkClient.getToken()
//   config.headers.Authorization = `Bearer ${token}`
//   return config
// })

export const customInstance = <T>(config: AxiosRequestConfig): Promise<T> => {
  return AXIOS_INSTANCE(config).then(({ data }) => data)
}
