import { getAgentAvatarClasses } from '@/lib/agentColour'

const SIZE_CLASSES = {
  sm: 'h-6 w-6 text-caption font-semibold',
  md: 'h-9 w-9 text-label font-semibold',
} as const

interface AgentAvatarProps {
  id: string
  name: string
  size?: 'sm' | 'md'
}

export function AgentAvatar({ id, name, size = 'md' }: AgentAvatarProps) {
  const colour = getAgentAvatarClasses(id)
  return (
    <span
      aria-hidden="true"
      className={`inline-flex shrink-0 items-center justify-center rounded-md ${SIZE_CLASSES[size]} ${colour}`}
    >
      {name.charAt(0).toUpperCase()}
    </span>
  )
}
