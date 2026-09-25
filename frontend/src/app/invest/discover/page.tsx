import Link from "next/link";
import {
  getInvestDiscover,
  type InvestDiscover,
  type InvestDiscoverItem,
  type InvestDiscoverSection,
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
      <div className="w-full rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        Unusual activity could not load yet. Refresh or try again shortly.
      </div>
    );
  }

  const visibleSections = discover.sections;
  const unusualSection =
    visibleSections.find((section) => section.id === "unusual_activity") ??
    visibleSections[0] ??
    null;
  const sideSections = visibleSections.filter(
    (section) => section.id !== unusualSection?.id,
  );

  return (
    <div className="w-full space-y-4">
      <section className="rounded-2xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <div className="grid gap-5 p-5 lg:grid-cols-[minmax(0,1fr)_360px] sm:p-6">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              Discover
            </p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">
              What&apos;s moving
            </h2>
            <p className="mt-2 max-w-4xl text-sm leading-6 text-zinc-600 dark:text-zinc-400">
              {discover.narrative ?? discover.summary}
            </p>
            {discover.narrative ? (
              <p className="mt-2 text-sm text-zinc-500">{discover.summary}</p>
            ) : null}
          </div>
          <aside className="rounded-xl bg-zinc-50 p-4 dark:bg-zinc-900">
            <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
              Scan status
            </p>
            <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">
              Updated {new Date(discover.generated_at).toLocaleString()}
            </p>
            <div className="mt-4 grid grid-cols-3 gap-2 text-sm">
              <SummaryMetric
                label="Names"
                value={countForSection(unusualSection)}
              />
              <SummaryMetric
                label="Groups"
                value={countForId(visibleSections, "sector_moves")}
              />
              <SummaryMetric
                label="Board"
                value={countForId(visibleSections, "board_movers")}
              />
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <Link href="/invest/news" className={quickLinkClassName}>
                News
              </Link>
              <Link href="/invest/watchlist" className={quickLinkClassName}>
                Watchlist
              </Link>
              <Link href="/invest/markets" className={quickLinkClassName}>
                Markets
              </Link>
            </div>
          </aside>
        </div>
      </section>

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1.35fr)_minmax(340px,0.65fr)]">
        {unusualSection ? (
          <DiscoverSectionPanel section={unusualSection} featured />
        ) : null}

        <aside className="space-y-4">
          {sideSections.map((section) => (
            <DiscoverSectionPanel key={section.id} section={section} compact />
          ))}
          {discover.next_actions.length > 0 ? (
            <section className="rounded-2xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                Next
              </p>
              <div className="mt-4 space-y-3">
                {discover.next_actions.map((action, index) => (
                  <DiscoverCard
                    key={discoverItemKey("next_actions", action, index)}
                    item={action}
                    compact
                  />
                ))}
              </div>
            </section>
          ) : null}
        </aside>
      </div>
    </div>
  );
}

const quickLinkClassName =
  "rounded-lg border border-zinc-200 bg-white px-3 py-2 text-xs font-medium text-zinc-700 transition hover:bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-300 dark:hover:bg-zinc-900";

function DiscoverSectionPanel({
  compact = false,
  featured = false,
  section,
}: {
  compact?: boolean;
  featured?: boolean;
  section: InvestDiscoverSection;
}) {
  return (
    <section className="rounded-2xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <div className="border-b border-zinc-100 p-5 dark:border-zinc-900">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
              {section.id.replaceAll("_", " ")}
            </p>
            <h3 className="mt-1 text-lg font-semibold">{section.title}</h3>
          </div>
          <span className="rounded-md bg-zinc-100 px-2 py-1 text-xs font-medium text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300">
            {section.items.length}
          </span>
        </div>
        <p className="mt-2 text-sm leading-6 text-zinc-500">
          {section.description}
        </p>
      </div>
      <div
        className={
          featured
            ? "grid gap-3 p-5 lg:grid-cols-2"
            : "space-y-3 p-5"
        }
      >
        {section.items.map((item, index) => (
          <DiscoverCard
            key={discoverItemKey(section.id, item, index)}
            item={item}
            compact={compact}
          />
        ))}
      </div>
    </section>
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
      className={`h-full rounded-xl border border-zinc-200 bg-white p-4 transition dark:border-zinc-800 dark:bg-zinc-950 ${
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
          {item.metadata.filter(Boolean).map((value, index) => (
            <span
              key={`${value}-${index}`}
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

function SummaryMetric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-white p-2 dark:bg-zinc-950">
      <p className="text-[11px] uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 font-semibold tabular-nums">{value}</p>
    </div>
  );
}

function countForSection(section: InvestDiscoverSection | null) {
  return section ? String(section.items.length) : "0";
}

function countForId(sections: InvestDiscoverSection[], id: string) {
  return String(sections.find((section) => section.id === id)?.items.length ?? 0);
}

function discoverItemKey(sectionId: string, item: InvestDiscoverItem, index: number) {
  return [
    sectionId,
    item.href ?? "no-href",
    item.title,
    item.badge ?? "no-badge",
    index,
  ].join("|");
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
