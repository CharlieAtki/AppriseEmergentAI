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

      <DialogContent className="fixed left-1/2 top-1/2 max-h-[85vh] w-full max-w-3xl -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-xl border border-border bg-surface p-6 shadow-xl focus:outline-none sm:max-w-3xl">
          <DialogTitle className="text-title font-semibold text-foreground">
            Add panel
          </DialogTitle>
          <DialogDescription className="mt-1 text-body text-muted">
            Pick a panel to add to this page. You can drag, resize, or remove it
            afterward.
          </DialogDescription>

          <div className="mt-4 flex flex-col items-center gap-1">
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
            <span className="text-caption font-semibold uppercase tracking-architectural text-muted">
              {activeCategory}
            </span>
          </div>

          {/* One row per category page when there's room — every category
              currently has 2 panel types. flex-wrap (not nowrap+scroll) means
              a narrow viewport drops cards to a second row instead of ever
              showing a horizontal scrollbar. */}
          <div className="mt-6 flex flex-row flex-wrap gap-4">
            {visibleDefinitions.map((definition) => {
              const Icon = definition.icon;
              const sizeLabel = `${definition.defaultW} × ${definition.defaultH}`;
              return (
                <Button
                  key={definition.type}
                  onClick={() => handleAdd(definition.type)}
                  className="group flex min-h-56 w-64 flex-1 flex-col items-stretch justify-start gap-3 whitespace-normal rounded-lg border border-border bg-elevated p-4 text-left outline-none transition-colors hover:border-brand-primary hover:bg-hover focus-visible:ring-1 focus-visible:ring-brand-primary"
                >
                  <div className="h-24 w-full shrink-0">
                    <PanelFootprintPreview
                      w={definition.defaultW}
                      h={definition.defaultH}
                      icon={Icon}
                      sizeLabel={sizeLabel}
                    />
                  </div>
                  <div className="min-w-0 space-y-1.5">
                    <div className="flex min-w-0 items-center gap-1.5">
                      <Icon size={15} className="shrink-0 text-muted" />
                      <span className="truncate text-label font-semibold text-foreground">
                        {definition.label}
                      </span>
                    </div>
                    <p className="text-caption leading-relaxed text-secondary">
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
