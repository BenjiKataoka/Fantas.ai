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

// Portfolio "Your players": the same four columns as the real table, so the
// exposure dots and projection bars don't jump when the data lands.
export function PortfolioTableSkeleton({ rows = 8, leagues = 4 }) {
  const td = 'px-3 py-2.5'
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <Skeleton className="h-7 w-40" />
        <Skeleton className="h-3.5 w-64 max-w-[45%]" />
      </div>
      <div className="bg-surface border border-line rounded-xl">
        <table className="w-full table-fixed text-sm">
          <colgroup><col /><col className="w-14" /><col className="w-24" /><col className="w-60" /></colgroup>
          <thead>
            <tr>
              <th className={td}><Skeleton className="h-2.5 w-12" /></th>
              <th className={td}><Skeleton className="h-2.5 w-6" /></th>
              <th className={td}><Skeleton className="h-2.5 w-8 mx-auto" /></th>
              <th className={td}><Skeleton className="h-2.5 w-20" /></th>
            </tr>
          </thead>
          <tbody>
            {Array.from({ length: rows }).map((_, i) => (
              <tr key={i} className="border-t border-line/50">
                <td className={td}>
                  <div className="flex items-center gap-2.5">
                    <Skeleton className="size-3.5 shrink-0" />
                    <Skeleton className="h-8 w-1 rounded-full shrink-0" />
                    <Skeleton className="size-8 rounded-full shrink-0" />
                    <div className="min-w-0 space-y-1.5">
                      <div className="flex items-center gap-2">
                        <Skeleton className="h-3.5 w-32" />
                        {i % 4 === 1 && <Skeleton className="h-4 w-9 rounded" />}
                      </div>
                      <Skeleton className="h-2.5 w-10" />
                    </div>
                  </div>
                </td>
                <td className={td}><Skeleton className="h-3 w-7" /></td>
                <td className={td}><Skeleton className="h-4 w-14 mx-auto rounded-full" /></td>
                <td className={td}>
                  <div className="flex items-center gap-3">
                    <span className="flex gap-1">
                      {Array.from({ length: leagues }).map((_, d) => (
                        <Skeleton key={d} className="size-2 rounded-full" />
                      ))}
                    </span>
                    <Skeleton className="h-2.5 w-24" />
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
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

// Waivers: summary sentence, then the fixed-width free-agent table beside the sidebar.
// Uses the page's own colgroup so every placeholder sits in its real column.
export function WaiverSkeleton({ rows = 10 }) {
  const td = 'px-3 py-2.5'
  return (
    <div className="flex flex-col gap-6">
      <div className="space-y-2.5 max-w-2xl">
        <Skeleton className="h-4.5 w-full" />
        <Skeleton className="h-4.5 w-1/2" />
      </div>
      <div className="flex flex-col xl:flex-row gap-6 items-start">
        <div className="w-fit max-w-full overflow-x-auto bg-surface border border-line rounded-xl">
          <table className="w-[51.5rem] table-fixed">
            <colgroup>
              <col className="w-72" /><col className="w-14" /><col className="w-20" /><col className="w-20" />
              <col className="w-20" /><col className="w-32" /><col className="w-28" />
            </colgroup>
            <thead>
              <tr>
                <th className={td}><Skeleton className="h-2.5 w-10" /></th>
                <th className={td}><Skeleton className="h-2.5 w-6" /></th>
                {[10, 10, 12, 16].map((w, i) => (
                  <th key={i} className={td}><Skeleton className="h-2.5 ml-auto" style={{ width: `${w * 0.25}rem` }} /></th>
                ))}
                <th className={td} />
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: rows }).map((_, i) => (
                <tr key={i} className="border-t border-line/50">
                  <td className={td}>
                    <div className="flex items-center gap-2.5">
                      <Skeleton className="size-8 rounded-full shrink-0" />
                      <div className="space-y-1.5">
                        <div className="flex items-center gap-2"><Skeleton className="h-3.5 w-28" /><Skeleton className="h-3 w-7" /></div>
                        {i % 3 === 1 && <Skeleton className="h-2.5 w-44" />}
                      </div>
                    </div>
                  </td>
                  <td className={td}><Skeleton className="h-3 w-6" /></td>
                  <td className={td}><Skeleton className="h-3.5 w-8 ml-auto" /></td>
                  <td className={td}><Skeleton className="h-3.5 w-8 ml-auto" /></td>
                  <td className={td}><Skeleton className="h-3.5 w-11 ml-auto" /></td>
                  <td className={td}>
                    <Skeleton className="h-3 w-20 ml-auto" />
                    {i % 4 === 1 && <Skeleton className="h-3 w-24 ml-auto mt-1.5" />}
                  </td>
                  <td className={`${td} pl-5`}><Skeleton className="h-6 w-full rounded-md" /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="w-full xl:w-72 shrink-0 flex flex-col gap-4">
          <div className="bg-surface border border-line rounded-xl p-4">
            <Skeleton className="h-3.5 w-24" />
            <Skeleton className="h-2.5 w-52 mt-2 mb-4" />
            <div className="space-y-2.5">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="flex items-center gap-2">
                  <Skeleton className="h-2.5 w-8" /><Skeleton className="h-3 flex-1" /><Skeleton className="h-3 w-8" />
                </div>
              ))}
            </div>
          </div>
          <div className="px-1 space-y-2.5">
            {[90, 100, 60, 70].map(w => <Skeleton key={w} className="h-2.5" style={{ width: `${w}%` }} />)}
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
