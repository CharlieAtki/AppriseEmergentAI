'use client'

import { Dialog, DialogContent, DialogTitle, DialogDescription } from '@/components/ui/dialog'
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogCancel,
  AlertDialogAction,
} from '@/components/ui/alert-dialog'
import { Checkbox } from '@/components/ui/checkbox'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { FieldLabel } from '@/components/ui/field'
import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import {
  useGetWorkspaceCoordinationConfigWorkspacesWorkspaceIdCoordinationConfigGet,
  useUpdateWorkspaceCoordinationConfigWorkspacesWorkspaceIdCoordinationConfigPatch,
  getGetWorkspaceCoordinationConfigWorkspacesWorkspaceIdCoordinationConfigGetQueryKey,
} from '@/api/generated/coordination-config/coordination-config'
import {
  useGetWorkspaceBiddingConfigWorkspacesWorkspaceIdBiddingConfigGet,
  useUpdateWorkspaceBiddingConfigWorkspacesWorkspaceIdBiddingConfigPatch,
  getGetWorkspaceBiddingConfigWorkspacesWorkspaceIdBiddingConfigGetQueryKey,
} from '@/api/generated/bidding-config/bidding-config'
import type { CoordinationConfigResponse } from '@/api/generated/model'
import { COORDINATION_CONFIG_FIELDS, type ConfigFieldMeta } from '@/config/coordinationConfigFields'
import { BIDDING_CONFIG_FIELDS, type BiddingFieldMeta } from '@/config/biddingConfigFields'
import { Badge } from '@/components/ui/Badge'
import { toast } from 'sonner'

interface WorkspaceSettingsModalProps {
  workspaceId: string
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

function workspaceOverrideOf(data: CoordinationConfigResponse, key: string): number | null {
  return key === 'max_delegation_depth'
    ? data.workspace_max_delegation_depth_override
    : data.workspace_decompose_difficulty_threshold_override
}

// max_delegation_depth's real ceiling is dynamic (platform-configured), not a
// static field-schema value — see CoordinationConfigResponse.platform_max_delegation_depth_ceiling.
function maxOf(data: CoordinationConfigResponse, key: string): number | undefined {
  return key === 'max_delegation_depth' ? data.platform_max_delegation_depth_ceiling : undefined
}

function fieldError(state: FieldState, field: { min?: number }, max: number | undefined): string | null {
  if (!state.overrideEnabled) return null
  if (state.value.trim() === '') return 'This field is required.'
  const num = Number(state.value)
  if (Number.isNaN(num)) return 'Enter a valid number.'
  if (field.min !== undefined && num < field.min) return `Must be at least ${field.min}.`
  if (max !== undefined && num > max) return `Must be at most ${max}.`
  return null
}

// Bidding config has no dynamic ceiling (unlike max_delegation_depth) — its
// field.max (1) is a plain static bound, so bidding fields reuse fieldError
// directly with field.max instead of needing their own maxOf()-equivalent.

export function WorkspaceSettingsModal({ workspaceId, open, onOpenChange }: WorkspaceSettingsModalProps) {
  const [fields, setFields] = useState<Record<string, FieldState>>({})
  const [initialFields, setInitialFields] = useState<Record<string, FieldState>>({})
  const [biddingFields, setBiddingFields] = useState<Record<string, FieldState>>({})
  const [biddingInitialFields, setBiddingInitialFields] = useState<Record<string, FieldState>>({})
  const [confirmDiscardOpen, setConfirmDiscardOpen] = useState(false)
  const queryClient = useQueryClient()

  const { data, isLoading, isError, refetch } = useGetWorkspaceCoordinationConfigWorkspacesWorkspaceIdCoordinationConfigGet(
    workspaceId,
    { query: { enabled: open } },
  )
  const {
    data: biddingData,
    isLoading: biddingIsLoading,
    isError: biddingIsError,
    refetch: refetchBidding,
  } = useGetWorkspaceBiddingConfigWorkspacesWorkspaceIdBiddingConfigGet(workspaceId, { query: { enabled: open } })

  useEffect(() => {
    if (!open || !data) return
    const next: Record<string, FieldState> = {}
    for (const field of COORDINATION_CONFIG_FIELDS) {
      const override = workspaceOverrideOf(data, field.key)
      next[field.key] = {
        overrideEnabled: override !== null,
        value: String(override ?? effectiveValueOf(data, field.key)),
      }
    }
    setFields(next)
    setInitialFields(next)
  }, [open, data])

  useEffect(() => {
    if (!open || !biddingData) return
    const next: Record<string, FieldState> = {
      bid_score_threshold: {
        overrideEnabled: biddingData.workspace_bid_score_threshold_override !== null,
        value: String(
          biddingData.workspace_bid_score_threshold_override ?? biddingData.effective_bid_score_threshold,
        ),
      },
    }
    setBiddingFields(next)
    setBiddingInitialFields(next)
  }, [open, biddingData])

  const isDirty = JSON.stringify(fields) !== JSON.stringify(initialFields)
  const biddingIsDirty = JSON.stringify(biddingFields) !== JSON.stringify(biddingInitialFields)

  function handleOpenChange(next: boolean) {
    if (!next && (isDirty || biddingIsDirty)) {
      setConfirmDiscardOpen(true)
      return
    }
    onOpenChange(next)
  }

  const { mutate, isPending } = useUpdateWorkspaceCoordinationConfigWorkspacesWorkspaceIdCoordinationConfigPatch({
    mutation: {
      onSuccess: () => {
        void queryClient.invalidateQueries({
          queryKey: getGetWorkspaceCoordinationConfigWorkspacesWorkspaceIdCoordinationConfigGetQueryKey(workspaceId),
        })
        toast('Workspace settings saved')
      },
      onError: () => {
        toast.error('Failed to update workspace settings')
      },
    },
  })

  const { mutate: mutateBidding, isPending: biddingIsPending } =
    useUpdateWorkspaceBiddingConfigWorkspacesWorkspaceIdBiddingConfigPatch({
      mutation: {
        onSuccess: () => {
          void queryClient.invalidateQueries({
            queryKey: getGetWorkspaceBiddingConfigWorkspacesWorkspaceIdBiddingConfigGetQueryKey(workspaceId),
          })
          toast('Bid scoring settings saved')
        },
        onError: () => {
          toast.error('Failed to update bid scoring settings')
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

  function toggleBiddingOverride(checked: boolean) {
    setBiddingFields((prev) => ({
      ...prev,
      bid_score_threshold: checked
        ? {
            overrideEnabled: true,
            value: prev.bid_score_threshold?.value ?? String(biddingData!.effective_bid_score_threshold),
          }
        : { overrideEnabled: false, value: prev.bid_score_threshold?.value ?? '' },
    }))
  }

  const hasErrors = COORDINATION_CONFIG_FIELDS.some((field) => {
    const state = fields[field.key]
    return state && data && fieldError(state, field, maxOf(data, field.key)) !== null
  })

  const biddingState = biddingFields.bid_score_threshold
  const biddingField = BIDDING_CONFIG_FIELDS[0] as BiddingFieldMeta
  const biddingError = biddingState ? fieldError(biddingState, biddingField, biddingField.max) : null

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    mutate({
      workspaceId,
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

  function handleBiddingSubmit(e: React.FormEvent) {
    e.preventDefault()
    mutateBidding({
      workspaceId,
      data: {
        bid_score_threshold: biddingState?.overrideEnabled ? Number(biddingState.value) : null,
      },
    })
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className="fixed left-1/2 top-1/2 w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-xl focus:outline-none">
          <DialogTitle className="text-title font-semibold text-foreground">
            Workspace settings
          </DialogTitle>
          <DialogDescription className="mt-1 text-body text-muted">
            Override the organisation's defaults for this workspace only.
          </DialogDescription>

          <form onSubmit={handleSubmit} className="mt-5 space-y-4">
            <p className="text-label font-semibold uppercase tracking-architectural text-muted">
              Coordination
            </p>

            {isLoading &&
              COORDINATION_CONFIG_FIELDS.map((field) => (
                <div key={field.key} className="space-y-1.5">
                  <Skeleton className="h-4 w-32 bg-elevated" />
                  <Skeleton className="h-3 w-full bg-elevated" />
                  <Skeleton className="h-9 w-full rounded-lg bg-elevated" />
                </div>
              ))}

            {isError && (
              <div className="space-y-2 rounded-lg border border-error/30 bg-error/10 px-3 py-2.5">
                <p className="text-caption text-error">Couldn't load workspace settings.</p>
                <Button
                  type="button"
                  onClick={() => refetch()}
                  className="text-caption font-medium text-error underline underline-offset-2"
                >
                  Try again
                </Button>
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
                      <FieldLabel className="text-label font-medium text-secondary">{field.label}</FieldLabel>
                      <div className="flex items-center gap-2">
                        <Badge status={source} />
                        <div className="flex items-center gap-1.5 text-caption text-muted">
                          <Checkbox
                            id={`workspace-override-${field.key}`}
                            checked={state.overrideEnabled}
                            onCheckedChange={(checked) => toggleOverride(field, checked)}
                            className="h-4 w-4 rounded border-border bg-elevated data-checked:border-brand-primary data-checked:bg-brand-primary data-checked:text-background focus-visible:ring-brand-primary"
                          />
                          <FieldLabel htmlFor={`workspace-override-${field.key}`}>Override</FieldLabel>
                        </div>
                      </div>
                    </div>
                    <p className="text-caption text-muted">{field.description}</p>
                    {clamped && (
                      <p className="text-caption text-warning">
                        Clamped to the platform ceiling ({data.platform_max_delegation_depth_ceiling}).
                      </p>
                    )}
                    <Input
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

            <div className="flex justify-end pt-1">
              <Button
                type="submit"
                disabled={isPending || !data || hasErrors}
                className="rounded-lg bg-brand-primary px-4 py-2 text-body font-medium text-background transition-colors hover:bg-brand-hover disabled:opacity-50"
              >
                {isPending ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </form>

          <div className="my-5 border-t border-border" />

          <form onSubmit={handleBiddingSubmit} className="space-y-4">
            <p className="text-label font-semibold uppercase tracking-architectural text-muted">
              Bid scoring
            </p>

            {biddingIsLoading && (
              <div className="space-y-1.5">
                <Skeleton className="h-4 w-32 bg-elevated" />
                <Skeleton className="h-3 w-full bg-elevated" />
                <Skeleton className="h-9 w-full rounded-lg bg-elevated" />
              </div>
            )}

            {biddingIsError && (
              <div className="space-y-2 rounded-lg border border-error/30 bg-error/10 px-3 py-2.5">
                <p className="text-caption text-error">Couldn't load bid scoring settings.</p>
                <Button
                  type="button"
                  onClick={() => refetchBidding()}
                  className="text-caption font-medium text-error underline underline-offset-2"
                >
                  Try again
                </Button>
              </div>
            )}

            {biddingData && biddingState && (
              <div className="space-y-1.5">
                <div className="flex items-center justify-between gap-2">
                  <FieldLabel className="text-label font-medium text-secondary">{biddingField.label}</FieldLabel>
                  <div className="flex items-center gap-2">
                    <Badge status={biddingData.bid_score_threshold_source} />
                    <div className="flex items-center gap-1.5 text-caption text-muted">
                      <Checkbox
                        id="workspace-override-bid_score_threshold"
                        checked={biddingState.overrideEnabled}
                        onCheckedChange={(checked) => toggleBiddingOverride(checked)}
                        className="h-4 w-4 rounded border-border bg-elevated data-checked:border-brand-primary data-checked:bg-brand-primary data-checked:text-background focus-visible:ring-brand-primary"
                      />
                      <FieldLabel htmlFor="workspace-override-bid_score_threshold">Override</FieldLabel>
                    </div>
                  </div>
                </div>
                <p className="text-caption text-muted">{biddingField.description}</p>
                <Input
                  type="number"
                  inputMode={biddingField.type === 'integer' ? 'numeric' : 'decimal'}
                  min={biddingField.min}
                  max={biddingField.max}
                  step={biddingField.step}
                  disabled={!biddingState.overrideEnabled || biddingIsPending}
                  value={
                    biddingState.overrideEnabled ? biddingState.value : String(biddingData.effective_bid_score_threshold)
                  }
                  onChange={(e) =>
                    setBiddingFields((prev) => ({
                      ...prev,
                      bid_score_threshold: { overrideEnabled: true, value: e.target.value },
                    }))
                  }
                  className={`w-full rounded-lg border bg-elevated px-3 py-2 text-body text-foreground disabled:opacity-50 focus:outline-none focus:ring-1 ${
                    biddingError
                      ? 'border-error focus:border-error focus:ring-error'
                      : 'border-border focus:border-brand-primary focus:ring-brand-primary'
                  }`}
                />
                {biddingError && <p className="text-caption text-error">{biddingError}</p>}
              </div>
            )}

            <div className="flex justify-end pt-1">
              <Button
                type="submit"
                disabled={biddingIsPending || !biddingData || biddingError !== null}
                className="rounded-lg bg-brand-primary px-4 py-2 text-body font-medium text-background transition-colors hover:bg-brand-hover disabled:opacity-50"
              >
                {biddingIsPending ? 'Saving…' : 'Save'}
              </Button>
            </div>
          </form>

      </DialogContent>

      <AlertDialog open={confirmDiscardOpen} onOpenChange={setConfirmDiscardOpen}>
        <AlertDialogContent className="fixed left-1/2 top-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-xl focus:outline-none">
          <AlertDialogTitle className="text-title font-semibold text-foreground">
            Discard changes?
          </AlertDialogTitle>
          <AlertDialogDescription className="mt-1 text-body text-muted">
            You have unsaved changes to this workspace's settings. Closing now will discard them.
          </AlertDialogDescription>
          <AlertDialogFooter className="mt-6 -mx-0 -mb-0 flex justify-end gap-2 rounded-none border-t-0 bg-transparent p-0">
            <AlertDialogCancel className="rounded-lg px-4 py-2 text-body text-muted transition-colors hover:text-foreground">
              Keep editing
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => onOpenChange(false)}
              className="rounded-lg bg-error px-4 py-2 text-body font-medium text-white transition-colors hover:opacity-90"
            >
              Discard
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  )
}
