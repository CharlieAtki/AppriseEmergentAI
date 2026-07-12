'use client'

import { Button } from '@/components/ui/button'

import { Popover, PopoverTrigger, PopoverContent, PopoverArrow } from '@/components/ui/popover'
import { IconInfo, IconCopy, IconCheck } from '@/lib/icons'
import { useState } from 'react'
import { format } from 'date-fns'
import type { WorkspaceResponse } from '@/api/generated/model'
import { Badge } from '@/components/ui/Badge'

interface WorkspaceInfoPopoverProps {
  workspace: WorkspaceResponse
}

export function WorkspaceInfoPopover({ workspace }: WorkspaceInfoPopoverProps) {
  const [copied, setCopied] = useState(false)

  function copyId() {
    void navigator.clipboard.writeText(workspace.id)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const createdAt = workspace.created_at
    ? format(new Date(workspace.created_at), 'dd MMM yyyy, HH:mm')
    : null

  return (
    <Popover>
      <PopoverTrigger
        render={
          <Button
            aria-label="Workspace info"
            variant="ghost"
            size="icon"
            className="rounded-md p-1.5 text-muted transition-colors hover:bg-hover hover:text-foreground"
          />
        }
      >
        <IconInfo size={14} />
      </PopoverTrigger>

      <PopoverContent
        side="top"
        align="start"
        sideOffset={6}
        className="popover-content z-50 w-72 rounded-xl border border-border bg-elevated p-4 shadow-xl"
      >
          <p className="mb-3 text-label font-semibold uppercase tracking-architectural text-muted">
            Workspace details
          </p>

          <dl className="space-y-3">
            <div>
              <dt className="text-caption text-muted">ID</dt>
              <dd className="mt-0.5 flex items-center gap-1.5">
                <span className="flex-1 truncate font-mono text-code text-secondary">
                  {workspace.id}
                </span>
                <Button
                  onClick={copyId}
                  aria-label="Copy workspace ID"
                  variant="ghost"
                  size="icon"
                  className="shrink-0 text-muted transition-colors hover:text-foreground"
                >
                  {copied ? <IconCheck size={12} className="text-success" /> : <IconCopy size={12} />}
                </Button>
              </dd>
            </div>

            <div>
              <dt className="text-caption text-muted">Status</dt>
              <dd className="mt-0.5">
                <Badge status={workspace.status} />
              </dd>
            </div>

            <div>
              <dt className="text-caption text-muted">Agents</dt>
              <dd className="mt-0.5 text-caption text-secondary">
                {workspace.agent_count ?? 0} agent{(workspace.agent_count ?? 0) !== 1 ? 's' : ''}
              </dd>
            </div>

            {createdAt && (
              <div>
                <dt className="text-caption text-muted">Created</dt>
                <dd className="mt-0.5 text-caption text-secondary">{createdAt}</dd>
              </div>
            )}

            <div>
              <dt className="text-caption text-muted">Webhook URL</dt>
              <dd className="mt-0.5 truncate font-mono text-code text-secondary">
                {workspace.result_webhook_url ?? '—'}
              </dd>
            </div>
          </dl>

        <PopoverArrow />
      </PopoverContent>
    </Popover>
  )
}
