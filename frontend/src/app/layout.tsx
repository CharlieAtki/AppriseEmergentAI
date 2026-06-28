import type { Metadata } from 'next'
import { ClerkProvider } from '@clerk/nextjs'
import { Space_Grotesk, Manrope, JetBrains_Mono } from 'next/font/google'
import { Providers } from './providers'
import './globals.css'

const spaceGrotesk = Space_Grotesk({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-space-grotesk',
  display: 'swap',
})

const manrope = Manrope({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700'],
  variable: '--font-manrope',
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
        className={`${spaceGrotesk.variable} ${manrope.variable} ${jetbrainsMono.variable} h-full antialiased`}
      >
        <body className="min-h-full text-foreground">
          <Providers>{children}</Providers>
        </body>
      </html>
    </ClerkProvider>
  )
}
