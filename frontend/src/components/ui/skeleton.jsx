import { cn } from '@/lib/utils'

// Pulsing placeholder block for loading states.
export function Skeleton({ className, ...props }) {
  return <div className={cn('animate-pulse rounded-md bg-muted/60', className)} {...props} />
}
