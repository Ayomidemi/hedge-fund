"use client";

import Link from "next/link";
import { useMemo, useRef, useState, Fragment } from "react";
import { WatchlistButton } from "@/components/radar/WatchlistButton";
import { toast } from "@/components/ui/ToastProvider";
import { addRadarWatchlistItem, getMarketRadarDesk, removeRadarWatchlistItem, runMarketRadarScan,
  type MarketRadarName, type MarketRadarOverview } from "@/lib/api";
import { filterRadarNames, hasDataGap, isSignal, type RadarSort, type RadarView } from "@/lib/radar-view";
import { tickerHubPath } from "@/lib/ticker-hub-path";

const control = "rounded-lg border border-rule bg-paper px-3 py-2 text-sm text-ink transition hover:bg-action focus-visible:outline-2 focus-visible:outline-sky-300 disabled:opacity-50";
const panel = "rounded-sm border border-rule bg-[var(--pease-paper)] dark:border-rule";
const PAGE_SIZE = 25;
const formatDate = (value?: string | null) => value && Number.isFinite(Date.parse(value))
  ? new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZone: "UTC" }).format(new Date(value)) + " UTC" : "Unavailable";
const number = (value: unknown, suffix = "", signed = false) => value !== null && value !== undefined && value !== "" && Number.isFinite(Number(value))
  ? `${signed && Number(value) > 0 ? "+" : ""}${Number(value).toLocaleString("en-US", { maximumFractionDigits: 2, minimumFractionDigits: suffix === "" ? 2 : 1 })}${suffix}` : "—";

export function MarketRadar({ initialOverview }: { initialOverview: MarketRadarOverview | null }) {
  const [updated, setUpdated] = useState<MarketRadarOverview | null>(null);
  const overview = updated && (!initialOverview || updated.generated_at >= initialOverview.generated_at) ? updated : initialOverview;
  const [market, setMarket] = useState("all");
  const [industry, setIndustry] = useState("");
  const [query, setQuery] = useState("");
  const [view, setView] = useState<RadarView>("all");
  const [sort, setSort] = useState<RadarSort>("priority");
  const [page, setPage] = useState(0);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [pending, setPending] = useState<"scan" | "refresh" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [watched, setWatched] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState<Set<string>>(new Set());
  const inFlight = useRef(false);
  const mutations = useRef(new Set<string>());
  const names = useMemo(() => (overview?.working_set ?? []).map(name =>
    name.ticker in watched ? { ...name, on_watchlist: watched[name.ticker] } : name), [overview, watched]);
  const marketNames = useMemo(() => names.filter(name => market === "all" || name.jurisdiction === market), [names, market]);
  const filtered = useMemo(() => filterRadarNames(names, { market, industry, query, view, sort }), [names, market, industry, query, view, sort]);
  const counts = { all: marketNames.length, signals: marketNames.filter(isSignal).length,
    watched: marketNames.filter(name => name.on_watchlist || name.in_portfolio).length, gaps: marketNames.filter(hasDataGap).length };
  const pages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const currentPage = Math.min(page, pages - 1);
  const visible = filtered.slice(currentPage * PAGE_SIZE, (currentPage + 1) * PAGE_SIZE);
  const groups = (overview?.industries ?? []).filter(group => market === "all" || group.jurisdiction === market);

  async function refresh(scan = false) {
    if (inFlight.current) return;
    inFlight.current = true;
    setPending(scan ? "scan" : "refresh"); setError(null);
    try {
      if (scan) {
        const run = await runMarketRadarScan({ jurisdictions: market === "all" ? undefined : [market] });
        if (run.status !== "completed") throw new Error("The scan did not complete. Previous observations are still displayed.");
        if (!run.jurisdictions_scanned.length) toast.error("No market is open for scanning. Previous observations are still displayed.");
      }
      setUpdated(await getMarketRadarDesk());
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Radar could not refresh. Please retry.");
    } finally { inFlight.current = false; setPending(null); }
  }
  async function toggleWatch(name: MarketRadarName) {
    if (mutations.current.has(name.ticker)) return;
    const previous = Boolean(name.on_watchlist);
    mutations.current.add(name.ticker); setBusy(new Set(mutations.current));
    setWatched(current => ({ ...current, [name.ticker]: !previous }));
    try {
      if (previous) await removeRadarWatchlistItem(name.ticker);
      else await addRadarWatchlistItem({ ticker: name.ticker, market: name.jurisdiction === "NG" ? "NG" : "US" });
    } catch (reason) {
      setWatched(current => ({ ...current, [name.ticker]: previous }));
      toast.error(reason instanceof Error ? reason.message : "Watchlist update failed.");
    } finally { mutations.current.delete(name.ticker); setBusy(new Set(mutations.current)); }
  }
  if (!overview) return <section className={`${panel} p-8`}>
    <h3 className="font-medium">Radar could not be loaded</h3>
    <p role="alert" className="my-3 text-sm text-zinc-500">{error ?? "Try loading the latest saved scan again."}</p>
    <button className={control} disabled={Boolean(pending)} onClick={() => void refresh()}>{pending ? "Loading…" : "Retry radar"}</button>
  </section>;
  const sessions = overview.sessions.filter(session => market === "all" || session.jurisdiction === market);
  const canScan = sessions.some(session => session.allows_discovery);
  // Row time identifies the displayed observations even if the last run skipped closed markets.
  const snapshotTime = names.reduce<string | null>((latest, name) => !latest || name.as_of > latest ? name.as_of : latest, null);

  return <div className="space-y-5">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-zinc-500">
        {sessions.map(session => <span key={session.jurisdiction} className="inline-flex items-center gap-2">
          <span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${session.is_open ? "bg-emerald-600" : "bg-zinc-400"}`} />{session.label}</span>)}
        <span>Snapshot {formatDate(snapshotTime)}</span>
      </div>
      <div className="flex gap-2">
        <button className={control} disabled={Boolean(pending)} onClick={() => void refresh()}>{pending === "refresh" ? "Refreshing…" : "Refresh"}</button>
        <button className={`${control} border-transparent bg-action text-action-ink hover:bg-action-hover`} disabled={Boolean(pending) || !canScan}
          title={canScan ? "Request a new market scan" : "Scans resume when a market opens"} onClick={() => void refresh(true)}>{pending === "scan" ? "Scanning…" : "Scan markets"}</button>
      </div>
    </div>
    {error ? <p role="alert" className="border-l-2 border-amber-500 bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-100">{error} Displayed data has not been refreshed.</p> : null}
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_230px]">
      <section className={`${panel} min-w-0`} aria-label="Radar observations" aria-busy={pending !== null}>
        <div className="flex flex-wrap items-center gap-3 border-b border-rule p-4 dark:border-rule">
          <input type="search" aria-label="Search radar" placeholder="Find a ticker, company or industry" value={query}
            onChange={event => { setQuery(event.target.value); setPage(0); }} className={`${control} min-w-0 flex-1 basis-56`} />
          <select aria-label="Market" className={control} value={market} onChange={event => { setMarket(event.target.value); setIndustry(""); setPage(0); }}>
            <option value="all">All markets</option><option value="US">United States</option><option value="NG">Nigeria</option>
          </select>
          <select aria-label="Sort observations" className={control} value={sort} onChange={event => { setSort(event.target.value as RadarSort); setPage(0); }}>
            <option value="priority">Priority first</option><option value="gainers">Biggest rises</option><option value="losers">Biggest falls</option><option value="volume">Relative volume</option>
          </select>
        </div>
        <div className="flex flex-wrap gap-x-5 gap-y-2 border-b border-rule px-4 dark:border-rule" role="group" aria-label="Observation filters">
          {([["all", "All names"], ["signals", "Priority signals"], ["watched", "Held & watched"], ["gaps", "Data gaps"]] as const).map(([key, label]) =>
            <button key={key} aria-pressed={view === key} onClick={() => { setView(key); setPage(0); }} className={`border-b-2 py-3 text-sm ${view === key ? "border-sky-400 font-semibold text-action-ink dark:text-sky-200" : "border-transparent text-muted"}`}>
              {label} <span className="ml-1 text-xs tabular-nums text-zinc-500">{counts[key]}</span></button>)}
        </div>
        <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-xs text-zinc-500">
          <p>{view === "signals" ? "P0/P1 observations still need execution and capital checks." : view === "gaps" ? "Missing history, incomplete quotes or prior-session observations." : "Daily price moves · volume compared with a completed daily average"}</p>
          {industry ? <button className="underline underline-offset-2" onClick={() => { setIndustry(""); setPage(0); }}>Clear industry filter ×</button> : null}
        </div>
        <table className="w-full table-fixed text-left text-sm">
          <thead className="border-y border-zinc-100 bg-zinc-50 text-[11px] text-zinc-500 dark:border-rule dark:bg-zinc-900">
            <tr><th className="w-[44%] px-4 py-2 font-medium sm:w-[35%]">Name</th><th className="px-2 py-2 text-right font-medium">Price / day</th>
              <th className="hidden px-3 py-2 text-right font-medium md:table-cell">Volume</th><th className="hidden px-3 py-2 font-medium lg:table-cell">Observation</th><th className="px-3 py-2 text-right font-medium">Details</th></tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {visible.map(name => <Fragment key={name.ticker}><tr className="hover:bg-hover dark:hover:bg-zinc-900/60">
              <td className="px-2 py-3 sm:px-4"><div className="flex min-w-0 items-center gap-1">
                <WatchlistButton ticker={name.ticker} watched={Boolean(name.on_watchlist)} busy={busy.has(name.ticker)} onClick={() => void toggleWatch(name)} />
                <div className="min-w-0"><Link prefetch={false} href={tickerHubPath(name.ticker)} className="font-semibold hover:underline">{name.ticker}</Link>
                  <p className="truncate text-xs text-zinc-500" title={name.name}>{name.name}</p></div></div></td>
              <td className="px-2 py-3 text-right tabular-nums"><span>{number(name.price)}</span><span className={`block text-xs ${Number(name.change_pct) > 0 ? "text-emerald-700 dark:text-emerald-400" : Number(name.change_pct) < 0 ? "text-rose-700 dark:text-rose-400" : "text-zinc-500"}`}>{number(name.change_pct, "%", true)}</span>
                <span className="block text-[10px] text-zinc-500">{name.currency}</span></td>
              <td className="hidden px-3 py-3 text-right tabular-nums text-zinc-600 md:table-cell dark:text-zinc-400">{number(name.volume_ratio, "×")}</td>
              <td className="hidden px-3 py-3 lg:table-cell"><span className="text-xs">{name.stale_reason || name.carried_forward ? "Awaiting quote" : name.radar_priority ? `${name.radar_priority} · ${name.change_pct && Number(name.change_pct) < 0 ? "Downward move" : "Unusual activity"}` : "Monitoring"}</span>
                <span className="block text-[11px] text-zinc-500">{name.in_portfolio ? "Held" : hasDataGap(name) ? "Data incomplete" : "History available"}</span></td>
              <td className="px-3 py-3 text-right"><button aria-label={`Details for ${name.ticker}`} aria-expanded={expanded === name.ticker} aria-controls={`radar-detail-${name.ticker}`} className="rounded-sm px-1 py-2 text-xs underline underline-offset-4" onClick={() => setExpanded(expanded === name.ticker ? null : name.ticker)}>{expanded === name.ticker ? "Close" : "View"}</button></td>
            </tr>{expanded === name.ticker ? <tr id={`radar-detail-${name.ticker}`}><td colSpan={5} className="bg-hover px-5 py-5 dark:bg-zinc-900">
              <div className="grid gap-4 text-xs sm:grid-cols-2"><div><p className="font-semibold">{name.radar_priority ? `${name.radar_priority} observation` : "Market observation"} · {name.industry || name.sector || "Unclassified"}</p>
                <p className="mt-2 leading-5 text-zinc-600 dark:text-zinc-400">{name.stale_reason || (name.carried_forward ? "Retained from an earlier session." : name.priority_reasons?.join(" · ") || "This name has not met an active priority threshold.")}</p>
                <Link prefetch={false} href={tickerHubPath(name.ticker)} className="mt-3 inline-block font-medium underline underline-offset-4">Open ticker analysis →</Link></div>
                <dl className="space-y-2"><Detail label="Quote observed" value={formatDate(name.source_as_of)} /><Detail label="Completed return samples" value={String(name.evidence.return_sample_count ?? "Unavailable")} /><Detail label="Versus sector" value={number(name.evidence.sector_relative_return_pct, "%", true)} /><Detail label="Relative volume" value={number(name.volume_ratio, "×")} /></dl>
              </div><p className="mt-4 text-[11px] text-zinc-500">Radar priority indicates activity or risk. It does not mean an order is ready to execute.</p>
            </td></tr> : null}</Fragment>)}
          </tbody>
        </table>
        {!visible.length ? <div className="px-5 py-14 text-center"><p className="font-medium">{names.length ? "No names match this view" : "Waiting for the first market scan"}</p>
          <p className="mt-2 text-sm text-zinc-500">{names.length ? "Try another market, industry or filter." : "Scheduled scans populate the radar when a market is open."}</p>
          {names.length ? <button className="mt-4 text-sm underline underline-offset-4" onClick={() => { setQuery(""); setIndustry(""); setView("all"); setMarket("all"); setPage(0); }}>Show all names</button> : null}</div> : null}
        <footer className="flex items-center justify-between gap-2 border-t border-rule px-4 py-3 text-xs text-zinc-500 dark:border-rule">
          <span role="status">{filtered.length ? `${currentPage * PAGE_SIZE + 1}–${Math.min((currentPage + 1) * PAGE_SIZE, filtered.length)} of ${filtered.length}` : "0 names"}</span>
          <div className="flex items-center gap-3"><button className="py-2 disabled:opacity-30" disabled={currentPage === 0} onClick={() => setPage(currentPage - 1)}>Previous</button><span>{currentPage + 1} / {pages}</span><button className="py-2 disabled:opacity-30" disabled={currentPage + 1 >= pages} onClick={() => setPage(currentPage + 1)}>Next</button></div>
        </footer>
      </section>
      <aside className="space-y-5">
        <section className={`${panel} p-4`}><h3 className="font-semibold">Industry view</h3><p className="mt-1 text-xs text-zinc-500">Filter the displayed sample</p>
          <div className="mt-4 max-h-96 space-y-1 overflow-y-auto"><button aria-pressed={!industry} onClick={() => { setIndustry(""); setPage(0); }} className={`flex w-full justify-between rounded-sm px-2 py-2 text-left text-sm ${!industry ? "bg-hover font-medium dark:bg-zinc-800" : "text-zinc-500"}`}>All industries <span>{marketNames.length}</span></button>
            {groups.map(group => { const key = `${group.jurisdiction}:${group.name}`; return <button key={key} aria-pressed={industry === key} onClick={() => { setIndustry(key); setPage(0); }} className={`flex w-full items-center justify-between gap-2 rounded-sm px-2 py-2 text-left text-xs ${industry === key ? "bg-hover font-semibold dark:bg-zinc-800" : "hover:bg-hover dark:hover:bg-zinc-900"}`}>
              <span className="min-w-0 truncate">{group.name}<span className="block text-[10px] font-normal text-zinc-500">{group.jurisdiction} · {group.name_count} names</span></span><span className="shrink-0 tabular-nums text-zinc-500">{number(group.median_change_pct, "%", true)}</span></button>; })}</div>
        </section>
        <section className="px-1 text-xs leading-5 text-zinc-500"><h3 className="mb-2 font-semibold text-zinc-700 dark:text-zinc-300">From observation to order</h3><p>Priority signals are screened for current quotes, confirmation, risk and available capital.</p>
          <Link href="/opportunity-queue" className="mt-3 inline-block font-medium text-zinc-900 underline underline-offset-4 dark:text-zinc-100">View executable orders →</Link>
          <p className="mt-4 border-t border-rule pt-4 dark:border-rule">This is a monitored sample, not the entire market. Missing data is shown explicitly.</p></section>
      </aside>
    </div>
  </div>;
}
function Detail({ label, value }: { label: string; value: string }) {
  return <div className="flex justify-between gap-3"><dt className="text-zinc-500">{label}</dt><dd className="text-right tabular-nums">{value}</dd></div>;
}
