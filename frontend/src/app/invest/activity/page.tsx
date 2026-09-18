import Link from "next/link";
import {
  getInvestActivity,
  type InvestProfileActivity,
} from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";
import { buttonSecondaryClassName } from "@/components/ui/form-styles";

export default async function InvestActivityPage() {
  const accessToken = await getServerAccessToken();
  let activity: InvestProfileActivity[] = [];
  let unavailable = false;

  try {
    activity = await getInvestActivity(100, { accessToken });
  } catch {
    unavailable = true;
  }

  if (unavailable) {
    return (
      <div className="mx-auto max-w-4xl rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        Invest activity could not load.
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-zinc-500">
              Invest activity
            </p>
            <h2 className="mt-1 text-2xl font-semibold">Activity</h2>
            <p className="mt-2 text-sm text-zinc-500">
              {activity.length} recent account event{activity.length === 1 ? "" : "s"}
            </p>
          </div>
          <Link href="/invest/profile" className={buttonSecondaryClassName}>
            Profile
          </Link>
        </div>
      </section>

      <section className="overflow-hidden rounded-2xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
        {activity.length > 0 ? (
          <div className="divide-y divide-zinc-100 dark:divide-zinc-900">
            {activity.map((item) => (
              <article key={`${item.event}-${item.occurred_at}`} className="px-5 py-4">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <div className="flex flex-wrap items-center gap-2 text-xs text-zinc-500">
                    <time dateTime={item.occurred_at}>
                      {formatDateTime(item.occurred_at)}
                    </time>
                    <span>{formatLabel(item.event)}</span>
                  </div>
                  <LevelBadge level={item.level} />
                </div>
                <p className="mt-2 text-sm leading-6 text-zinc-800 dark:text-zinc-200">
                  {item.message}
                </p>
              </article>
            ))}
          </div>
        ) : (
          <p className="px-5 py-10 text-center text-sm text-zinc-500">
            No Invest activity yet.
          </p>
        )}
      </section>
    </div>
  );
}

function LevelBadge({ level }: { level: string }) {
  const normalized = level.toLowerCase();
  const className =
    normalized === "error"
      ? "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-200"
      : normalized === "warning"
        ? "bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-200"
        : "bg-zinc-100 text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300";

  return (
    <span className={`rounded-md px-2 py-1 text-xs font-medium ${className}`}>
      {formatLabel(level)}
    </span>
  );
}

function formatLabel(value: string) {
  return value.replaceAll("_", " ");
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("en-US", {
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    month: "short",
    year: "numeric",
  }).format(new Date(value));
}
