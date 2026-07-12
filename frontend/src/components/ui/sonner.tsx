"use client"

import { Toaster as Sonner, type ToasterProps } from "sonner"
import { IconInfo, IconToastError, IconToastSuccess, IconToastWarning, IconSpinner } from "@/lib/icons"

// This app has one fixed dark theme (no next-themes / ThemeProvider, no
// light/dark toggle) — theme is hardcoded rather than read from a provider
// that doesn't exist.
const Toaster = ({ ...props }: ToasterProps) => {
  return (
    <Sonner
      theme="dark"
      className="toaster group"
      position="top-right"
      icons={{
        success: <IconToastSuccess className="size-4" />,
        info: <IconInfo className="size-4" />,
        warning: <IconToastWarning className="size-4" />,
        error: <IconToastError className="size-4" />,
        loading: <IconSpinner className="size-4 animate-spin" />,
      }}
      style={
        {
          "--normal-bg": "var(--color-popover)",
          "--normal-text": "var(--color-popover-foreground)",
          "--normal-border": "var(--color-border)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: "cn-toast",
        },
      }}
      {...props}
    />
  )
}

export { Toaster }
