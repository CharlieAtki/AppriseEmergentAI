'use client'

import * as Dialog from '@radix-ui/react-dialog'
import { useState } from 'react'
import { DASHBOARD_PANEL_CATEGORIES, DASHBOARD_PANEL_DEFINITIONS, type DashboardPanelCategory } from '@/lib/dashboardPanels'
import { IconAdd, IconClose } from '@/lib/icons'
import { useDashboardLayoutStore } from '@/stores/dashboardLayout'
import { PanelFootprintPreview } from './PanelFootprintPreview'
import { DashboardPagerArrow } from './DashboardPagerArrow'
import { DashboardPagerDots } from './DashboardPagerDots'

export function AddPanelDialog() {
  const [open, setOpen] = useState(false)
  const [categoryIndex, setCategoryIndex] = useState(0)
  const addPanel = useDashboardLayoutStore((state) => state.addPanel)
  const activeCategory: DashboardPanelCategory = DASHBOARD_PANEL_CATEGORIES[categoryIndex]!
  const visibleDefinitions = DASHBOARD_PANEL_DEFINITIONS.filter((d) => d.category === activeCategory)

  function handleAdd(type: string) {
    addPanel(type)
    setOpen(false)
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button className="flex items-center gap-2 rounded-lg bg-brand-primary px-4 py-2 text-body font-medium text-background transition-colors hover:bg-brand-hover">
          <IconAdd size={16} />
          Add panel
        </button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="dialog-overlay fixed inset-0 bg-background/60 backdrop-blur-sm" />
        <Dialog.Content className="dialog-content fixed left-1/2 top-1/2 w-full max-w-2xl -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-xl focus:outline-none">
          <Dialog.Title className="text-title font-semibold text-foreground">Add panel</Dialog.Title>
          <Dialog.Description className="mt-1 text-body text-muted">
            Pick a panel to add to this page. You can drag, resize, or remove it afterward.
          </Dialog.Description>

          <div className="mt-4 flex items-center justify-center gap-1">
            <DashboardPagerArrow
              direction="prev"
              disabled={categoryIndex === 0}
              onClick={() => setCategoryIndex((i) => Math.max(0, i - 1))}
            />
            <span className="min-w-20 text-center text-label font-semibold uppercase tracking-architectural text-foreground">
              {activeCategory}
            </span>
            <DashboardPagerDots page={categoryIndex} pageCount={DASHBOARD_PANEL_CATEGORIES.length} onChange={setCategoryIndex} />
            <DashboardPagerArrow
              direction="next"
              disabled={categoryIndex === DASHBOARD_PANEL_CATEGORIES.length - 1}
              onClick={() => setCategoryIndex((i) => Math.min(DASHBOARD_PANEL_CATEGORIES.length - 1, i + 1))}
            />
          </div>

          <div className="mt-3 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {visibleDefinitions.map((definition) => {
              const Icon = definition.icon
              return (
                <button
                  key={definition.type}
                  onClick={() => handleAdd(definition.type)}
                  className="flex flex-col gap-2.5 rounded-lg border border-border bg-elevated p-3 text-left outline-none transition-colors hover:border-brand-primary hover:bg-hover focus-visible:ring-1 focus-visible:ring-brand-primary"
                >
                  <PanelFootprintPreview w={definition.defaultW} h={definition.defaultH} />
                  <div className="flex items-center gap-1.5">
                    <Icon size={13} className="shrink-0 text-muted" />
                    <span className="text-label font-semibold text-foreground">{definition.label}</span>
                  </div>
                  <p className="text-caption text-muted">{definition.description}</p>
                </button>
              )
            })}
          </div>

          <Dialog.Close asChild>
            <button
              className="absolute right-4 top-4 rounded text-muted outline-none transition-colors hover:text-foreground focus-visible:ring-1 focus-visible:ring-brand-primary"
              aria-label="Close"
            >
              <IconClose size={16} />
            </button>
          </Dialog.Close>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
