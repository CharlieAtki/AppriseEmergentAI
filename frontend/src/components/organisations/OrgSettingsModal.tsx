'use client'

import * as Dialog from '@radix-ui/react-dialog'
import * as AlertDialog from '@radix-ui/react-alert-dialog'
import * as Checkbox from '@radix-ui/react-checkbox'
import { Check, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useGetOrgCoordinationConfigOrganisationsOrgIdCoordinationConfigGet,
  useUpdateOrgCoordinationConfigOrganisationsOrgIdCoordinationConfigPatch,
  getGetOrgCoordinationConfigOrganisationsOrgIdCoordinationConfigGetQueryKey,
} from '@/api/generated/coordination-config/coordination-config'
import type { CoordinationConfigResponse } from '@/api/generated/model'
import { COORDINATION_CONFIG_FIELDS, type ConfigFieldMeta } from '@/config/coordinationConfigFields'
import { Badge } from '@/components/ui/Badge'
import { useToastStore } from '@/stores/toast'

interface OrgSettingsModalProps {
  orgId: string
  open: boolean
  onOpenChange: (open: boolean) => void
}

interface FieldState {
  overrideEnabled: boolean
  value: string
}

function effectiveValueOf(data: CoordinationConfigResponse, key: string): number {
  return key === 'max_delegation_depth'
    ? data.effective_max_delegation_depth
    : data.effective_decompose_difficulty_threshold
}

function sourceOf(data: CoordinationConfigResponse, key: string): string {
  return key === 'max_delegation_depth' ? data.max_delegation_depth_source : data.decompose_difficulty_threshold_source
}

function orgOverrideOf(data: CoordinationConfigResponse, key: string): number | null {
  return key === 'max_delegation_depth'
    ? data.org_max_delegation_depth_override
    : data.org_decompose_difficulty_threshold_override
}

// max_delegation_depth's real ceiling is dynamic (platform-configured), not a
// static field-schema value — see CoordinationConfigResponse.platform_max_delegation_depth_ceiling.
function maxOf(data: CoordinationConfigResponse, key: string): number | undefined {
  return key === 'max_delegation_depth' ? data.platform_max_delegation_depth_ceiling : undefined
}

function fieldError(state: FieldState, field: ConfigFieldMeta, max: number | undefined): string | null {
  if (!state.overrideEnabled) return null
  if (state.value.trim() === '') return 'This field is required.'
  const num = Number(state.value)
  if (Number.isNaN(num)) return 'Enter a valid number.'
  if (field.min !== undefined && num < field.min) return `Must be at least ${field.min}.`
  if (max !== undefined && num > max) return `Must be at most ${max}.`
  return null
}

export function OrgSettingsModal({ orgId, open, onOpenChange }: OrgSettingsModalProps) {
  const [fields, setFields] = useState<Record<string, FieldState>>({})
  const [initialFields, setInitialFields] = useState<Record<string, FieldState>>({})
  const [confirmDiscardOpen, setConfirmDiscardOpen] = useState(false)
  const queryClient = useQueryClient()
  const { toast } = useToastStore()

  const { data, isLoading, isError, refetch } = useGetOrgCoordinationConfigOrganisationsOrgIdCoordinationConfigGet(
    orgId,
    { query: { enabled: open } },
  )

  useEffect(() => {
    if (!open || !data) return
    const next: Record<string, FieldState> = {}
    for (const field of COORDINATION_CONFIG_FIELDS) {
      const override = orgOverrideOf(data, field.key)
      next[field.key] = {
        overrideEnabled: override !== null,
        value: String(override ?? effectiveValueOf(data, field.key)),
      }
    }
    setFields(next)
    setInitialFields(next)
  }, [open, data])

  const isDirty = JSON.stringify(fields) !== JSON.stringify(initialFields)

  function handleOpenChange(next: boolean) {
    if (!next && isDirty) {
      setConfirmDiscardOpen(true)
      return
    }
    onOpenChange(next)
  }

  const { mutate, isPending } = useUpdateOrgCoordinationConfigOrganisationsOrgIdCoordinationConfigPatch({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({
          queryKey: getGetOrgCoordinationConfigOrganisationsOrgIdCoordinationConfigGetQueryKey(orgId),
        })
        toast({ title: 'Organisation settings saved', variant: 'default' })
        onOpenChange(false)
      },
      onError: () => {
        toast({ title: 'Failed to update organisation settings', variant: 'error' })
      },
    },
  })

  function toggleOverride(field: ConfigFieldMeta, checked: boolean) {
    setFields((prev) => ({
      ...prev,
      [field.key]: checked
        ? { overrideEnabled: true, value: prev[field.key]?.value ?? String(effectiveValueOf(data!, field.key)) }
        : { overrideEnabled: false, value: prev[field.key]?.value ?? '' },
    }))
  }

  const hasErrors = COORDINATION_CONFIG_FIELDS.some((field) => {
    const state = fields[field.key]
    return state && data && fieldError(state, field, maxOf(data, field.key)) !== null
  })

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    mutate({
      orgId,
      data: {
        max_delegation_depth: fields.max_delegation_depth?.overrideEnabled
          ? Number(fields.max_delegation_depth.value)
          : null,
        decompose_difficulty_threshold: fields.decompose_difficulty_threshold?.overrideEnabled
          ? Number(fields.decompose_difficulty_threshold.value)
          : null,
      },
    })
  }

  return (
    <Dialog.Root open={open} onOpenChange={handleOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay fixed inset-0 bg-background/60 backdrop-blur-sm" />
        <Dialog.Content className="dialog-content fixed left-1/2 top-1/2 w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-xl focus:outline-none">
          <Dialog.Title className="text-title font-semibold text-foreground">
            Organisation settings
          </Dialog.Title>
          <Dialog.Description className="mt-1 text-body text-muted">
            These defaults apply to every workspace in this organisation, unless a workspace overrides them.
          </Dialog.Description>

          <form onSubmit={handleSubmit} className="mt-5 space-y-4">
            <p className="text-label font-semibold uppercase tracking-architectural text-muted">
              Coordination
            </p>

            {isLoading &&
              COORDINATION_CONFIG_FIELDS.map((field) => (
                <div key={field.key} className="space-y-1.5 animate-pulse">
                  <div className="h-4 w-32 rounded bg-elevated" />
                  <div className="h-3 w-full rounded bg-elevated" />
                  <div className="h-9 w-full rounded-lg bg-elevated" />
                </div>
              ))}

            {isError && (
              <div className="space-y-2 rounded-lg border border-error/30 bg-error/10 px-3 py-2.5">
                <p className="text-caption text-error">Couldn't load organisation settings.</p>
                <button
                  type="button"
                  onClick={() => refetch()}
                  className="text-caption font-medium text-error underline underline-offset-2"
                >
                  Try again
                </button>
              </div>
            )}

            {data &&
              COORDINATION_CONFIG_FIELDS.map((field) => {
                const state = fields[field.key]
                if (!state) return null
                const source = sourceOf(data, field.key)
                const max = maxOf(data, field.key)
                const error = fieldError(state, field, max)
                const clamped = field.key === 'max_delegation_depth' && data.max_delegation_depth_clamped

                return (
                  <div key={field.key} className="space-y-1.5">
                    <div className="flex items-center justify-between gap-2">
                      <label className="text-label font-medium text-secondary">{field.label}</label>
                      <div className="flex items-center gap-2">
                        <Badge status={source} />
                        <div className="flex items-center gap-1.5 text-caption text-muted">
                          <Checkbox.Root
                            id={`org-override-${field.key}`}
                            checked={state.overrideEnabled}
                            onCheckedChange={(checked) => toggleOverride(field, checked === true)}
                            className="flex h-4 w-4 items-center justify-center rounded border border-border bg-elevated data-[state=checked]:border-brand-primary data-[state=checked]:bg-brand-primary focus:outline-none focus:ring-1 focus:ring-brand-primary"
                          >
                            <Checkbox.Indicator className="text-background">
                              <Check size={12} strokeWidth={3} />
                            </Checkbox.Indicator>
                          </Checkbox.Root>
                          <label htmlFor={`org-override-${field.key}`}>Override</label>
                        </div>
                      </div>
                    </div>
                    <p className="text-caption text-muted">{field.description}</p>
                    {clamped && (
                      <p className="text-caption text-warning">
                        Clamped to the platform ceiling ({data.platform_max_delegation_depth_ceiling}).
                      </p>
                    )}
                    <input
                      type="number"
                      inputMode={field.type === 'integer' ? 'numeric' : 'decimal'}
                      min={field.min}
                      max={max}
                      step={field.step}
                      disabled={!state.overrideEnabled || isPending}
                      value={state.overrideEnabled ? state.value : String(effectiveValueOf(data, field.key))}
                      onChange={(e) =>
                        setFields((prev) => ({
                          ...prev,
                          [field.key]: { overrideEnabled: true, value: e.target.value },
                        }))
                      }
                      className={`w-full rounded-lg border bg-elevated px-3 py-2 text-body text-foreground disabled:opacity-50 focus:outline-none focus:ring-1 ${
                        error
                          ? 'border-error focus:border-error focus:ring-error'
                          : 'border-border focus:border-brand-primary focus:ring-brand-primary'
                      }`}
                    />
                    {error && <p className="text-caption text-error">{error}</p>}
                  </div>
                )
              })}

            <div className="flex justify-end gap-2 pt-1">
              <Dialog.Close asChild>
                <button
                  type="button"
                  className="rounded-lg px-4 py-2 text-body text-muted transition-colors hover:text-foreground"
                >
                  Cancel
                </button>
              </Dialog.Close>
              <button
                type="submit"
                disabled={isPending || !data || hasErrors}
                className="rounded-lg bg-brand-primary px-4 py-2 text-body font-medium text-background transition-colors hover:bg-brand-hover disabled:opacity-50"
              >
                {isPending ? 'Saving…' : 'Save'}
              </button>
            </div>
          </form>

          <Dialog.Close asChild>
            <button
              className="absolute right-4 top-4 text-muted transition-colors hover:text-foreground"
              aria-label="Close"
            >
              <X size={16} />
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>

      <AlertDialog.Root open={confirmDiscardOpen} onOpenChange={setConfirmDiscardOpen}>
        <AlertDialog.Portal>
          <AlertDialog.Overlay className="dialog-overlay fixed inset-0 bg-background/60 backdrop-blur-sm" />
          <AlertDialog.Content className="dialog-content fixed left-1/2 top-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-xl focus:outline-none">
            <AlertDialog.Title className="text-title font-semibold text-foreground">
              Discard changes?
            </AlertDialog.Title>
            <AlertDialog.Description className="mt-1 text-body text-muted">
              You have unsaved changes to this organisation's coordination settings. Closing now will discard them.
            </AlertDialog.Description>
            <div className="mt-6 flex justify-end gap-2">
              <AlertDialog.Cancel asChild>
                <button
                  type="button"
                  className="rounded-lg px-4 py-2 text-body text-muted transition-colors hover:text-foreground"
                >
                  Keep editing
                </button>
              </AlertDialog.Cancel>
              <AlertDialog.Action asChild>
                <button
                  onClick={() => onOpenChange(false)}
                  className="rounded-lg bg-error px-4 py-2 text-body font-medium text-white transition-colors hover:opacity-90"
                >
                  Discard
                </button>
              </AlertDialog.Action>
            </div>
          </AlertDialog.Content>
        </AlertDialog.Portal>
      </AlertDialog.Root>
    </Dialog.Root>
  )
}
