'use client'

import { PanelShell } from '@/components/ui/PanelShell'

export default function WorkspacePage() {
  return (
    <div
      className="grid h-full grid-cols-2 gap-4"
      style={{ gridTemplateRows: 'minmax(0,1.5fr) minmax(0,1fr) minmax(0,1fr)' }}
    >
      <PanelShell title="Agent Pool" />
      <PanelShell title="Live Feed" />
      <PanelShell title="Agent Lanes" />
      <PanelShell title="Active Tasks" />
      <PanelShell title="Emergence Signal" />
      <PanelShell title="Workspace Stats" />
    </div>
  )
}
