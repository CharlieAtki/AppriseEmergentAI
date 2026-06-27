'use client'

import { useOrganization } from '@clerk/nextjs'
import { UserButton } from '@clerk/nextjs'

export default function OrgLayout({ children }: { children: React.ReactNode }) {
  const { organization } = useOrganization()

  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b border-border px-6 py-4">
        <div className="flex items-center gap-3">
          {organization?.imageUrl && (
            <img
              src={organization.imageUrl}
              alt={organization.name}
              className="h-7 w-7 rounded-md object-cover"
            />
          )}
          <span className="text-sm font-medium text-foreground">
            {organization?.name ?? ''}
          </span>
        </div>
        <UserButton />
      </header>
      <div className="flex-1">{children}</div>
    </div>
  )
}
