import Link from "next/link";
import {
  getInvestDiscover,
  type InvestDiscover,
  type InvestDiscoverItem,
} from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function InvestDiscoverPage() {
  const accessToken = await getServerAccessToken();
  let discover: InvestDiscover | null = null;

  try {
    discover = await getInvestDiscover({ accessToken });
  } catch {
    discover = null;
  }

  if (!discover) {
    return (
      <div className="mx-auto max-w-4xl rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        Unusual activity could not load yet. Refresh or try again shortly.
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl space-y-6">
      <section className="rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
        <p className="text-xs uppercase tracking-wide text-zinc-500">
          Discover
        </p>
        <h2 className="mt-1 text-2xl font-semibold">What&apos;s moving</h2>
        <p className="mt-3 max-w-3xl text-sm text-zinc-600 dark:text-zinc-400">
          {discover.summary}
        </p>
        <p className="mt-3 text-xs text-zinc-500">
          Updated {new Date(discover.generated_at).toLocaleString()}. Headlines
          stay on News; bills and bonds stay on Markets.
        </p>
      </section>

      {discover.next_actions.length > 0 ? (
        <section className="grid gap-3 md:grid-cols-2">
          {discover.next_actions.map((action) => (
            <DiscoverCard key={action.title} item={action} compact />
          ))}
        </section>
      ) : null}

      <div className="space-y-6">
        {discover.sections.map((section) => (
          <section key={section.id}>
            <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
              <div>
                <h3 className="text-lg font-semibold">{section.title}</h3>
                <p className="mt-1 text-sm text-zinc-500">{section.description}</p>
              </div>
            </div>
            <div className="grid gap-3 lg:grid-cols-2">
              {section.items.map((item) => (
                <DiscoverCard key={`${section.id}-${item.title}`} item={item} />
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

function DiscoverCard({
  item,
  compact = false,
}: {
  item: InvestDiscoverItem;
  compact?: boolean;
}) {
  const content = (
    <div
      className={`h-full rounded-2xl border border-zinc-200 bg-white p-5 transition dark:border-zinc-800 dark:bg-zinc-950 ${
        item.href ? "hover:bg-zinc-50 dark:hover:bg-zinc-900" : ""
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="font-semibold">{item.title}</p>
          {item.subtitle ? (
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">{item.subtitle}</p>
          ) : null}
        </div>
        {item.badge ? (
          <span className={`shrink-0 rounded-md px-2 py-1 text-xs font-medium ${toneClass(item.tone)}`}>
            {item.badge}
          </span>
        ) : null}
      </div>
      {item.metadata.length > 0 ? (
        <div className={`mt-4 flex flex-wrap gap-2 ${compact ? "text-[11px]" : "text-xs"}`}>
          {item.metadata.filter(Boolean).map((value) => (
            <span
              key={value}
              className="rounded-md bg-zinc-100 px-2 py-1 text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300"
            >
              {value}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );

  if (!item.href) {
    return content;
  }

  if (item.href.startsWith("http")) {
    return (
      <a href={item.href} target="_blank" rel="noreferrer">
        {content}
      </a>
    );
  }

  return <Link href={item.href}>{content}</Link>;
}

function toneClass(tone: string) {
  if (tone === "positive") {
    return "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200";
  }
  if (tone === "negative") {
    return "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-200";
  }
  if (tone === "income") {
    return "bg-amber-50 text-amber-800 dark:bg-amber-950 dark:text-amber-200";
  }
  return "bg-zinc-100 text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300";
}
