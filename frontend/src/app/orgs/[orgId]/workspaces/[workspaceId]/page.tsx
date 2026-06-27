'use client'

import { use } from 'react'

export default function WorkspacePage({
  params,
}: {
  params: Promise<{ workspaceId: string }>
}) {
  const { workspaceId } = use(params)

  return (
    <main className="flex flex-col gap-6 p-8">
      <h1 className="text-2xl font-semibold tracking-tight text-foreground">
        Workspace {workspaceId}
      </h1>
      <p className="text-sm text-muted">Dashboard coming soon.</p>
    </main>
  )
}
