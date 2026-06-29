const COLOUR_CLASSES = [
  'bg-brand-primary/15 text-brand-primary',
  'bg-brand-accent/15 text-brand-accent',
  'bg-brand-highlight/15 text-brand-highlight',
] as const

const SIZE_CLASSES = {
  sm: 'h-6 w-6 text-caption font-semibold',
  md: 'h-9 w-9 text-label font-semibold',
} as const

interface WorkspaceAvatarProps {
  name: string
  size: 'sm' | 'md'
}

export function WorkspaceAvatar({ name, size }: WorkspaceAvatarProps) {
  const colour = COLOUR_CLASSES[name.charCodeAt(0) % COLOUR_CLASSES.length]
  return (
    <span
      aria-hidden="true"
      className={`inline-flex shrink-0 items-center justify-center rounded-md ${SIZE_CLASSES[size]} ${colour}`}
    >
      {name.charAt(0).toUpperCase()}
    </span>
  )
}
