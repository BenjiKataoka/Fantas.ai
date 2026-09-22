import { cn } from '@/lib/utils'

// Loading placeholder with a sweeping shimmer (daisyUI-style), see .shimmer in index.css.
export function Skeleton({ className, ...props }) {
  return <div className={cn('shimmer rounded-md', className)} {...props} />
}
