import type { Metadata } from 'next'
import { ClerkProvider } from '@clerk/nextjs'
import { Inter, JetBrains_Mono } from 'next/font/google'
import { Providers } from './providers'
import './globals.css'

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  variable: '--font-jetbrains',
})

export const metadata: Metadata = {
  title: 'Apprise',
  description: 'Multi-tenant agent platform',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <ClerkProvider
      appearance={{
        variables: {
          colorBackground: '#0a0a0f',
          colorForeground: '#ededed',
          colorMutedForeground: '#d4d4d8',
          colorInput: '#141418',
          colorNeutral: '#ededed',
          colorPrimary: 'oklch(65% 0.2 165)',
        },
      }}
    >
      <html
        lang="en"
        className={`${inter.variable} ${jetbrainsMono.variable} h-full antialiased`}
      >
        <body className="min-h-full bg-background text-foreground">
          <Providers>{children}</Providers>
        </body>
      </html>
    </ClerkProvider>
  )
}
