import { Skeleton } from '@/components/ui/skeleton'

// Roster / lineup table placeholder — a header strip plus N player rows.
export function TableSkeleton({ rows = 8 }) {
  return (
    <div className="rounded-xl border border-line bg-surface overflow-hidden">
      <div className="bg-raised border-b border-line px-3 py-2.5">
        <Skeleton className="h-3 w-28" />
      </div>
      <div className="divide-y divide-line/40">
        {Array.from({ length: rows }).map((_, i) => (
          <div key={i} className="flex items-center gap-3 px-3 py-3">
            <Skeleton className="h-8 w-8 rounded-full" />
            <div className="flex-1 space-y-1.5">
              <Skeleton className="h-3.5 w-40" />
              <Skeleton className="h-2.5 w-16" />
            </div>
            <Skeleton className="h-3.5 w-10" />
            <Skeleton className="h-3.5 w-10" />
            <Skeleton className="h-5 w-14 rounded" />
          </div>
        ))}
      </div>
    </div>
  )
}

// Card feed placeholder — for news, tracker, and admin lists.
export function CardListSkeleton({ count = 5 }) {
  return (
    <div className="flex flex-col gap-3">
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="bg-surface border border-line rounded-xl p-4 flex gap-3">
          <Skeleton className="h-10 w-10 rounded-full" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3 w-32" />
            <Skeleton className="h-3.5 w-3/4" />
            <Skeleton className="h-5 w-20 rounded" />
          </div>
        </div>
      ))}
    </div>
  )
}
