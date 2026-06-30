'use client'

import * as Popover from '@radix-ui/react-popover'
import { useState, useEffect, useRef } from 'react'
import { format } from 'date-fns'
import { Badge } from '@/components/ui/Badge'
import { IconInfo, IconCopy, IconCheck } from '@/lib/icons'
import type { AgentResponse } from '@/api/generated/fastAPI.schemas'

interface AgentInfoPopoverProps {
  agent: AgentResponse
}

export function AgentInfoPopover({ agent }: AgentInfoPopoverProps) {
  const [open, setOpen] = useState(false)
  const [copied, setCopied] = useState(false)
  const contentRef = useRef<HTMLDivElement>(null)

  // ReactFlow's pan handler uses a capture-phase native listener that stops propagation
  // before Radix's document-level dismiss listener can fire. We attach our own
  // capture-phase listener so it runs first and closes the popover on any outside click.
  useEffect(() => {
    if (!open) return
    function handlePointerDown(e: PointerEvent) {
      if (contentRef.current && !contentRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    window.addEventListener('pointerdown', handlePointerDown, { capture: true })
    return () => window.removeEventListener('pointerdown', handlePointerDown, { capture: true })
  }, [open])

  function copyId() {
    void navigator.clipboard.writeText(agent.id)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  const skillCount = agent.skills ? Object.keys(agent.skills).length : 0
  const createdAt = format(new Date(agent.created_at), 'dd MMM yyyy, HH:mm')

  return (
    <Popover.Root open={open} onOpenChange={setOpen}>
      <Popover.Trigger asChild>
        <button
          aria-label="Agent info"
          className="rounded-md p-1.5 text-muted transition-colors hover:bg-hover hover:text-foreground"
        >
          <IconInfo size={13} />
        </button>
      </Popover.Trigger>

      <Popover.Portal>
        <Popover.Content
          ref={contentRef}
          side="top"
          align="end"
          sideOffset={6}
          className="popover-content z-50 w-64 rounded-xl border border-border bg-elevated p-4 shadow-xl"
        >
          <p className="mb-3 text-label font-semibold uppercase tracking-architectural text-muted">
            Agent details
          </p>

          <dl className="space-y-3">
            <div>
              <dt className="text-caption text-muted">ID</dt>
              <dd className="mt-0.5 flex items-center gap-1.5">
                <span className="flex-1 truncate font-mono text-code text-secondary">
                  {agent.id}
                </span>
                <button
                  onClick={copyId}
                  aria-label="Copy agent ID"
                  className="shrink-0 text-muted transition-colors hover:text-foreground"
                >
                  {copied
                    ? <IconCheck size={12} className="text-success" />
                    : <IconCopy size={12} />
                  }
                </button>
              </dd>
            </div>

            <div>
              <dt className="text-caption text-muted">Status</dt>
              <dd className="mt-0.5">
                <Badge status={agent.status} />
              </dd>
            </div>

            <div>
              <dt className="text-caption text-muted">Influence</dt>
              <dd className="mt-0.5 text-caption text-secondary">
                {agent.influence != null ? agent.influence.toFixed(4) : '—'}
              </dd>
            </div>

            <div>
              <dt className="text-caption text-muted">Skills</dt>
              <dd className="mt-0.5 text-caption text-secondary">
                {skillCount} acquired
              </dd>
            </div>

            <div>
              <dt className="text-caption text-muted">Created</dt>
              <dd className="mt-0.5 text-caption text-secondary">{createdAt}</dd>
            </div>
          </dl>

          <Popover.Arrow className="fill-border" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  )
}
