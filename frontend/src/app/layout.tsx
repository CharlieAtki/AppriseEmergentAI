import type { Metadata } from 'next'
import { ClerkProvider } from '@clerk/nextjs'
import { Inter, JetBrains_Mono } from 'next/font/google'
import { Providers } from './providers'
import './globals.css'

const inter = Inter({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-inter',
  display: 'swap',
})

const jetbrainsMono = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400'],
  variable: '--font-jetbrains',
  display: 'swap',
})

export const metadata: Metadata = {
  title: {
    default: 'Apprise',
    template: '%s — Apprise',
  },
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
          colorPrimary: 'oklch(49.1% 0.057 148.8)',
        },
      }}
    >
      <html
        lang="en"
        className={`${inter.variable} ${jetbrainsMono.variable} h-full antialiased`}
      >
        <body className="min-h-full text-foreground">
          <Providers>{children}</Providers>
        </body>
      </html>
    </ClerkProvider>
  )
}
