export default function InvestLoading() {
  return (
    <div className="w-full space-y-4">
      <div className="h-32 animate-pulse rounded-2xl bg-zinc-200/80 dark:bg-zinc-800" />
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="h-56 animate-pulse rounded-2xl bg-zinc-200/80 dark:bg-zinc-800" />
        <div className="h-56 animate-pulse rounded-2xl bg-zinc-200/80 dark:bg-zinc-800" />
      </div>
    </div>
  );
}
