import { Skeleton } from '@/components/ui/skeleton'

// Roster / lineup table placeholder, a header strip plus N player rows.
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

function RecapRow() {
  return (
    <div className="flex items-center gap-3 px-3 py-2.5 border-t border-line/50">
      <Skeleton className="h-3 w-6" />
      <Skeleton className="h-6 w-6 rounded-full" />
      <Skeleton className="h-3.5 w-32" />
      <div className="ml-auto flex gap-8">
        <Skeleton className="h-3.5 w-8" />
        <Skeleton className="h-3.5 w-8" />
        <Skeleton className="h-3.5 w-8" />
      </div>
    </div>
  )
}

// Recap page: summary sentence, then the player table beside the accuracy card.
export function RecapSkeleton({ starters = 9, bench = 5 }) {
  return (
    <div className="flex flex-col gap-6">
      <div className="space-y-2.5 max-w-2xl">
        <Skeleton className="h-4.5 w-full" />
        <Skeleton className="h-4.5 w-2/3" />
      </div>
      <div className="grid lg:grid-cols-[1fr_320px] gap-6 items-start">
        <div className="bg-surface border border-line rounded-xl overflow-hidden">
          <div className="flex items-center gap-3 px-3 py-3">
            <Skeleton className="h-2.5 w-6" />
            <Skeleton className="h-2.5 w-16" />
            <div className="ml-auto flex gap-8">
              <Skeleton className="h-2.5 w-8" /><Skeleton className="h-2.5 w-8" /><Skeleton className="h-2.5 w-8" />
            </div>
          </div>
          {Array.from({ length: starters }).map((_, i) => <RecapRow key={`s${i}`} />)}
          <div className="border-t border-line px-3 pt-4 pb-2"><Skeleton className="h-2.5 w-10" /></div>
          {Array.from({ length: bench }).map((_, i) => <RecapRow key={`b${i}`} />)}
        </div>
        <div className="bg-surface border border-line rounded-xl p-5">
          <Skeleton className="h-4 w-48" />
          <Skeleton className="h-3 w-56 mt-2 mb-5" />
          <div className="flex flex-col gap-4">
            {[70, 80, 90, 100].map(w => (
              <div key={w}>
                <div className="flex justify-between"><Skeleton className="h-3 w-20" /><Skeleton className="h-3 w-24" /></div>
                <Skeleton className="h-1.5 mt-2 rounded-full" style={{ width: `${w}%` }} />
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}

// Card feed placeholder, for news, tracker, and admin lists.
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
