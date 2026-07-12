"use client";

import { useState } from "react";

type UsePagedIndexInput =
  { pageCount: number } | { itemCount: number; pageSize: number };

interface UsePagedIndexResult {
  page: number;
  pageCount: number;
  setPage: (page: number) => void;
  goPrev: () => void;
  goNext: () => void;
  canGoPrev: boolean;
  canGoNext: boolean;
}

function resolvePageCount(input: UsePagedIndexInput): number {
  return "pageCount" in input
    ? input.pageCount
    : Math.max(1, Math.ceil(input.itemCount / input.pageSize));
}

// Bounds-checked pagination state shared by every local (non-store-backed)
// pager in the dashboard. Uses React's "adjust state during render" pattern
// (see usePageDirection.ts) to clamp `page` the same render its inputs
// shrink — e.g. a panel resize lowering pageSize, or a filter shrinking
// itemCount — rather than an effect, which would flash an out-of-range page.
export function usePagedIndex(input: UsePagedIndexInput): UsePagedIndexResult {
  const pageCount = resolvePageCount(input);
  const [page, setPageState] = useState(0);

  const clampedPage = Math.min(page, pageCount - 1);
  if (clampedPage !== page) {
    setPageState(clampedPage);
  }

  function setPage(next: number) {
    setPageState(Math.max(0, Math.min(pageCount - 1, next)));
  }

  return {
    page: clampedPage,
    pageCount,
    setPage,
    goPrev: () => setPage(clampedPage - 1),
    goNext: () => setPage(clampedPage + 1),
    canGoPrev: clampedPage > 0,
    canGoNext: clampedPage < pageCount - 1,
  };
}
