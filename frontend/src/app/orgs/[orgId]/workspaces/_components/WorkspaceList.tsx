'use client'

import { useState } from 'react'
import { Input } from '@/components/ui/input'
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group'
import { Skeleton } from '@/components/ui/skeleton'
import { IconGridView, IconListView, IconSearch } from '@/lib/icons'
import { useParams } from 'next/navigation'
import { useListWorkspacesWorkspacesGet } from '@/api/generated/workspaces/workspaces'
import { WorkspaceGrid } from '@/components/workspaces/WorkspaceGrid'

type View = 'grid' | 'list'

export function WorkspaceList() {
  const { orgId } = useParams<{ orgId: string }>()
  const [query, setQuery] = useState('')
  const [view, setView] = useState<View>('grid')
  const { data, isPending, isError } = useListWorkspacesWorkspacesGet()

  const allWorkspaces = data ?? []
  const workspaces = query
    ? allWorkspaces.filter((ws) =>
        ws.name.toLowerCase().includes(query.toLowerCase())
      )
    : allWorkspaces

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-heading font-bold text-foreground">Workspaces</h1>
          {!isPending && !isError && (
            <span className="inline-flex items-center rounded-full bg-elevated px-2.5 py-0.5 text-label font-medium text-muted tabular-nums">
              {allWorkspaces.length}
            </span>
          )}
        </div>
        <p className="mt-1 text-body text-secondary">Select a workspace to open its dashboard.</p>
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-3">
        <div className="relative w-64">
          <IconSearch size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none" />
          <Input
            type="search"
            placeholder="Search workspaces..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full rounded-lg border border-border bg-elevated py-2 pl-9 pr-3 text-body text-foreground placeholder:text-muted focus:border-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary"
          />
        </div>
        <ToggleGroup value={[view]} onValueChange={(values) => values[0] && setView(values[0] as View)} spacing={1}>
          <ToggleGroupItem
            aria-label="Grid view"
            aria-pressed={view === 'grid'}
            onClick={() => setView('grid')}
            className={`rounded-md p-1.5 transition-colors ${
              view === 'grid' ? 'bg-hover text-foreground' : 'text-muted hover:text-foreground'
            }`}
          >
            <IconGridView size={15} />
          </ToggleGroupItem>
          <ToggleGroupItem
            aria-label="List view"
            aria-pressed={view === 'list'}
            onClick={() => setView('list')}
            className={`rounded-md p-1.5 transition-colors ${
              view === 'list' ? 'bg-hover text-foreground' : 'text-muted hover:text-foreground'
            }`}
          >
            <IconListView size={15} />
          </ToggleGroupItem>
        </ToggleGroup>
      </div>

      {/* Content */}
      {isPending && !isError && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-36 rounded-lg bg-surface motion-reduce:animate-none" />
          ))}
        </div>
      )}

      {isError && (
        <p className="text-body text-error">
          Failed to load workspaces. Please refresh the page.
        </p>
      )}

      {!isPending && !isError && (
        <>
          {query && workspaces.length === 0 && (
            <p className="text-body text-muted">No workspaces match &ldquo;{query}&rdquo;.</p>
          )}
          <WorkspaceGrid workspaces={workspaces} orgId={orgId} view={view} />
        </>
      )}
    </div>
  )
}
