'use client'

import { useAuth } from '@clerk/nextjs'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ReactQueryDevtools } from '@tanstack/react-query-devtools'
import { IconContext } from '@phosphor-icons/react'
import { useEffect, useState } from 'react'

import { setAuthTokenGetter } from '@/api/client'
import { ICON_WEIGHT } from '@/lib/iconConfig'
import { Toaster } from '@/components/ui/sonner'

function AxiosAuthSync() {
  const { getToken } = useAuth()

  useEffect(() => {
    setAuthTokenGetter(getToken)
    return () => setAuthTokenGetter(null)
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
      <IconContext.Provider value={{ weight: ICON_WEIGHT }}>
        <AxiosAuthSync />
        {children}
        <Toaster />
        <ReactQueryDevtools initialIsOpen={false} />
      </IconContext.Provider>
    </QueryClientProvider>
  )
}
