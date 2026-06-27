'use client'

import { use } from 'react'

export default function WorkspacePage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { id } = use(params)

  return (
    <main className="flex flex-col gap-6 p-8">
      <h1 className="text-2xl font-semibold tracking-tight">Workspace {id}</h1>
      <p className="text-foreground/60 text-sm">Dashboard coming soon.</p>
    </main>
  )
}
