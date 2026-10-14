export function RadarSkeleton() {
  return <div role="status" aria-label="Loading market radar" className="rounded-sm border border-zinc-200 bg-[var(--pease-paper)] p-5 dark:border-zinc-800">
    <p className="mb-5 text-sm text-zinc-500">Loading market observations…</p>
    <div aria-hidden="true" className="space-y-4 motion-safe:animate-pulse">
      <div className="h-10 w-full rounded bg-zinc-100 dark:bg-zinc-800" />
      {Array.from({ length: 6 }, (_, i) => <div key={i} className="h-12 border-b border-zinc-100 dark:border-zinc-800" />)}
    </div>
  </div>;
}
