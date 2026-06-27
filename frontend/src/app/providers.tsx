'use client'

import { useAuth } from '@clerk/nextjs'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { useEffect, useState } from 'react'

import { AXIOS_INSTANCE } from '@/api/client'

function AxiosAuthSync() {
  const { getToken } = useAuth()

  useEffect(() => {
    const id = AXIOS_INSTANCE.interceptors.request.use(async (config) => {
      try {
        const token = await getToken()
        if (token) config.headers.Authorization = `Bearer ${token}`
      } catch {
        // no-op: unauthenticated requests proceed without the header
      }
      return config
    })
    return () => AXIOS_INSTANCE.interceptors.request.eject(id)
  }, [getToken])

  return null
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 30_000,
            refetchOnWindowFocus: true,
          },
        },
      }),
  )

  return (
    <QueryClientProvider client={queryClient}>
      <AxiosAuthSync />
      {children}
      <ReactQueryDevtools initialIsOpen={false} />
    </QueryClientProvider>
  )
}
