"use client";

import { Button } from "@/components/ui/button";

import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "@/components/ui/dialog";
import { useState } from "react";
import {
  DASHBOARD_PANEL_CATEGORIES,
  DASHBOARD_PANEL_DEFINITIONS,
  type DashboardPanelCategory,
} from "@/lib/dashboardPanels";
import { IconAdd } from "@/lib/icons";
import { useDashboardLayoutStore } from "@/stores/dashboardLayout";
import { usePagedIndex } from "@/hooks/dashboard/usePagedIndex";
import { PanelFootprintPreview } from "./PanelFootprintPreview";
import { DashboardPagerArrow } from "./DashboardPagerArrow";
import { DashboardPagerDots } from "./DashboardPagerDots";

export function AddPanelDialog() {
  const [open, setOpen] = useState(false);
  const {
    page: categoryIndex,
    setPage: setCategoryIndex,
    goPrev,
    goNext,
    canGoPrev,
    canGoNext,
  } = usePagedIndex({ pageCount: DASHBOARD_PANEL_CATEGORIES.length });
  const addPanel = useDashboardLayoutStore((state) => state.addPanel);
  const activeCategory: DashboardPanelCategory =
    DASHBOARD_PANEL_CATEGORIES[categoryIndex]!;
  const visibleDefinitions = DASHBOARD_PANEL_DEFINITIONS.filter(
    (d) => d.category === activeCategory,
  );

  function handleAdd(type: string) {
    addPanel(type);
    setOpen(false);
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button className="flex items-center gap-2 rounded-lg bg-brand-primary px-4 py-2 text-body font-medium text-background transition-colors hover:bg-brand-hover" />
        }
      >
        <IconAdd size={16} />
        Add panel
      </DialogTrigger>

      <DialogContent className="fixed left-1/2 top-1/2 w-full max-w-3xl -translate-x-1/2 -translate-y-1/2 rounded-xl border border-border bg-surface p-6 shadow-xl focus:outline-none">
          <DialogTitle className="text-title font-semibold text-foreground">
            Add panel
          </DialogTitle>
          <DialogDescription className="mt-1 text-body text-muted">
            Pick a panel to add to this page. You can drag, resize, or remove it
            afterward.
          </DialogDescription>

          <div className="mt-4 flex items-center justify-between gap-3 rounded-lg border border-border bg-elevated/40 px-3 py-2">
            <div className="flex items-center gap-1.5">
              <DashboardPagerArrow
                direction="prev"
                disabled={!canGoPrev}
                onClick={goPrev}
              />
              <DashboardPagerDots
                page={categoryIndex}
                pageCount={DASHBOARD_PANEL_CATEGORIES.length}
                onChange={setCategoryIndex}
              />
              <DashboardPagerArrow
                direction="next"
                disabled={!canGoNext}
                onClick={goNext}
              />
            </div>
            <span className="text-label font-semibold uppercase tracking-architectural text-foreground">
              {activeCategory}
            </span>
          </div>

          <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
            {visibleDefinitions.map((definition) => {
              const Icon = definition.icon;
              const sizeLabel = `${definition.defaultW} × ${definition.defaultH}`;
              return (
                <Button
                  key={definition.type}
                  onClick={() => handleAdd(definition.type)}
                  className="group flex h-full w-full min-h-52 flex-col items-stretch justify-start gap-3 whitespace-normal rounded-lg border border-border bg-elevated p-4 text-left outline-none transition-colors hover:border-brand-primary hover:bg-hover focus-visible:ring-1 focus-visible:ring-brand-primary"
                >
                  <div className="h-20 w-full shrink-0">
                    <PanelFootprintPreview
                      w={definition.defaultW}
                      h={definition.defaultH}
                    />
                  </div>
                  <div className="min-w-0 space-y-2">
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-1.5">
                        <Icon size={13} className="shrink-0 text-muted" />
                        <span className="truncate text-label font-semibold text-foreground">
                          {definition.label}
                        </span>
                      </div>
                      <span className="shrink-0 rounded-full border border-border bg-background px-2 py-0.5 text-[10px] font-semibold uppercase tracking-architectural text-muted">
                        {sizeLabel}
                      </span>
                    </div>
                    <p className="text-caption leading-relaxed text-secondary line-clamp-3">
                      {definition.description}
                    </p>
                  </div>
                </Button>
              );
            })}
          </div>
      </DialogContent>
    </Dialog>
  );
}
