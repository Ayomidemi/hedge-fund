"use client";

import Link from "next/link";
import { useEffect, useId, useRef, useState } from "react";
import {
  getPaperFund,
  setCapitalTradingMode,
  type PaperFundOrder,
  type PaperFundOverview,
} from "@/lib/api";
import { CapitalBalanceSummary, capitalMoney } from "@/components/portfolio/CapitalBalanceSummary";
import { PortfolioDashboard } from "@/components/portfolio/PortfolioDashboard";
import { tickerHubPath } from "@/lib/ticker-hub-path";
import { CapitalIcon } from "@/components/ui/CapitalIcon";
import { toast } from "@/components/ui/ToastProvider";

const timestamps = new Intl.DateTimeFormat("en-US", {
  month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short",
});
const panel = "rounded-2xl border border-zinc-200/80 bg-white dark:border-zinc-800/80 dark:bg-[#111316]";

const money = capitalMoney;

function when(value: string | null) {
  return value && Number.isFinite(Date.parse(value)) ? timestamps.format(new Date(value)) : "Awaiting first cycle";
}

export function PaperFundPanel({
  initialOverview,
  mode = "dashboard",
}: {
  initialOverview: PaperFundOverview | null;
  mode?: "dashboard" | "queue" | "radar";
}) {
  const [overview, setOverview] = useState(initialOverview);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const actionInFlight = useRef(false);
  const hasSnapshot = useRef(initialOverview !== null);
  const requestVersion = useRef(0);

  useEffect(() => {
    let cancelled = false;
    let refreshing = false;
    async function refresh() {
      if (cancelled || refreshing || actionInFlight.current) return;
      refreshing = true;
      const version = ++requestVersion.current;
      try {
        const data = await getPaperFund();
        if (!cancelled && version === requestVersion.current) {
          hasSnapshot.current = true;
          setOverview(data);
          setError(null);
        }
      } catch {
        if (!cancelled && version === requestVersion.current) {
          setError(hasSnapshot.current
            ? "Updates are unavailable. Displayed balances are from the last successful refresh."
            : "The Capital account is unavailable. Retry to load balances and trading controls.");
        }
      } finally {
        refreshing = false;
      }
    }
    function refreshWhenVisible() {
      if (document.visibilityState !== "visible" || actionInFlight.current) return;
      void refresh();
    }
    // A failed server render should recover as soon as the browser can reach the API.
    if (!hasSnapshot.current) void refresh();
    const timer = window.setInterval(refreshWhenVisible, 30_000);
    window.addEventListener("online", refreshWhenVisible);
    document.addEventListener("visibilitychange", refreshWhenVisible);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      window.removeEventListener("online", refreshWhenVisible);
      document.removeEventListener("visibilitychange", refreshWhenVisible);
    };
  }, []);

  async function act(action: "refresh" | "manual" | "automatic") {
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    const version = ++requestVersion.current;
    setPending(true);
    setError(null);
    try {
      const data = action === "refresh" ? await getPaperFund() : await setCapitalTradingMode(action);
      if (version === requestVersion.current) {
        hasSnapshot.current = true;
        setOverview(data);
      }
      if (action !== "refresh") {
        toast.success(action === "automatic" ? "Automatic mode enabled." : "Manual mode: automatic buys and sells stopped.");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Capital request failed.");
    } finally {
      actionInFlight.current = false;
      setPending(false);
    }
  }

  const run = overview?.run;
  const queued = overview?.orders.filter((order) => order.status === "pending") ?? [];
  const positions = overview?.orders.filter((order) => order.status === "open") ?? [];
  const history = overview?.orders.filter((order) => !["pending", "open"].includes(order.status)) ?? [];
  const loading = overview === null && error === null;
  const automatic = overview?.trading_mode === "automatic";
  const staleCycle = Boolean(automatic && run && run.status !== "completed" && overview
    && Date.parse(overview.generated_at) - Date.parse(run.last_cycle_at ?? run.started_at) > 90_000);
  const executionStatus = !overview ? "Connecting" : !automatic ? "Automatic trading off"
    : !run ? "Awaiting engine" : run.status === "halted" ? "Trading halted"
    : run.status === "completed" ? "Review complete" : run.status === "liquidating" ? "Closing positions"
    : run.status === "paused" ? "Execution paused" : staleCycle ? "Engine delayed"
    : queued.length ? "Waiting for limit fills" : "Monitoring opportunities";

  const controls = <div className="flex flex-wrap items-center gap-2">
    <div role="group" aria-label="Trading mode" className="inline-flex rounded-lg bg-zinc-100 p-1 dark:bg-zinc-800/70">
      {(["manual", "automatic"] as const).map((value) => <button key={value} type="button"
        aria-pressed={overview?.trading_mode === value} disabled={pending || !overview || overview.trading_mode === value}
        onClick={() => void act(value)}
        className={`rounded-md px-3.5 py-2 text-xs font-medium capitalize transition focus-visible:outline-2 focus-visible:outline-emerald-600 ${pending || !overview ? "opacity-50" : ""} ${overview?.trading_mode === value ? "bg-white text-emerald-800 shadow-sm dark:bg-zinc-700 dark:text-emerald-200" : "text-zinc-500 hover:text-zinc-900 dark:hover:text-white"}`}>
        {value === "automatic" ? <span className="mr-1.5 inline-block h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" /> : null}{value}
      </button>)}
    </div>
    <button type="button" disabled={pending} onClick={() => void act("refresh")} aria-label="Refresh Capital" title={error ? "Retry loading Capital" : "Refresh Capital"}
      className="rounded-lg border border-zinc-200 bg-white p-2.5 text-zinc-500 transition hover:bg-zinc-50 disabled:opacity-50 dark:border-zinc-800 dark:bg-zinc-900 dark:hover:bg-zinc-800"><CapitalIcon name="refresh" className={`h-4 w-4 ${pending ? "animate-spin" : ""}`} /></button>
  </div>;

  return <div className="mx-auto max-w-[1440px] space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-4">
      <div>
        <h2 className="text-2xl font-semibold tracking-tight">{mode === "queue" ? "Opportunity queue" : mode === "radar" ? "Your capital" : "Portfolio overview"}</h2>
        <p className="mt-1 text-xs text-zinc-500">{overview?.capital?.portfolio.name ?? "Capital account"}</p>
      </div>
      {controls}
    </div>
    {!overview ? <p role="status" className="text-sm text-zinc-500">{loading ? "Loading your trading settings…" : "Balances unavailable"}</p> : null}
    {error ? <p role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">{error}</p> : null}
    {overview && !automatic ? <p role="status" className="border-l-2 border-amber-400 pl-3 text-xs leading-5 text-zinc-500">Manual mode stops all automatic buys and sells, including stop and target exits. Existing holdings remain in Capital.</p> : null}
    {staleCycle ? <p role="status" className="rounded-xl bg-amber-50 p-4 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">The engine has not reported a cycle for over 90 seconds. Automatic execution may be delayed.</p> : null}
    {run?.halt_reason ? <p role="status" className="rounded-xl bg-amber-50 p-4 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">{run.halt_reason}</p> : null}
    {run?.status === "liquidating" ? <p className="text-sm text-zinc-500">Positions will close when eligible quotes are available. Profit or loss remains provisional until every position closes.</p> : null}

    <section className={`${panel} p-5 sm:p-7`} aria-label="Capital account overview">
      <div className="mb-5 flex flex-wrap items-center justify-between gap-2 text-[11px] text-zinc-500 dark:text-zinc-400">
        <span className="flex items-center gap-1.5"><span className="h-1 w-1 rounded-full bg-emerald-500" aria-hidden="true" />Paper execution · USD</span>
        <span>{overview ? `Updated ${when(overview.generated_at)}` : "Balances unavailable"}</span>
      </div>
      {overview?.capital ? <CapitalBalanceSummary capital={overview.capital} run={run ?? null} compact={mode !== "dashboard"} /> : <p className="py-8 text-sm text-zinc-500">{loading ? "Loading account balances…" : "Account balances could not be loaded."}</p>}
    </section>

    {overview && mode === "dashboard" ? <>
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_300px]">
        <section className={`${panel} overflow-hidden`}>
          <div className="flex flex-wrap items-start justify-between gap-3 px-5 pt-5 sm:px-7 sm:pt-6">
            <div><h3 className="text-sm font-semibold">Performance</h3><p className="mt-1 text-[11px] text-zinc-500">Account value over the current review</p></div>
            {run ? <span className="rounded-md bg-zinc-50 px-2.5 py-1.5 text-[11px] text-zinc-500 dark:bg-zinc-800">{new Date(run.started_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })} – {new Date(run.ends_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</span> : null}
          </div>
          <div className="px-5 sm:px-7">
            {run ? <EquityChart history={overview.equity_history} startingCash={run.starting_cash} /> : <div className="flex min-h-48 items-center justify-center text-center text-xs text-zinc-500">Enable Automatic to begin performance tracking.</div>}
          </div>
          {run ? <div className="border-t border-zinc-100 px-5 py-5 dark:border-zinc-800/80 sm:px-7">
            <dl className="grid grid-cols-2 gap-x-5 gap-y-4 sm:grid-cols-4">
              <div><dt className="text-[11px] text-zinc-500">Net profit / loss</dt><dd className={`mt-1.5 text-lg font-medium tabular-nums ${Number(run.total_pnl) < 0 ? "text-red-600 dark:text-red-400" : Number(run.total_pnl) > 0 ? "text-emerald-700 dark:text-emerald-400" : ""}`}>{money(run.total_pnl)}</dd><dd className="mt-1 text-[11px] text-zinc-500 dark:text-zinc-400">All time · {Number(run.return_pct).toFixed(2)}%</dd></div>
              <Rule label="Realized" value={money(run.realized_pnl)} />
              <Rule label="Unrealized" value={money(run.unrealized_pnl)} />
              <Rule label="Max. drawdown" value={`${Number(run.max_drawdown_pct).toFixed(2)}%`} />
            </dl>
            <details className="mt-4 text-[11px] leading-5 text-zinc-500 dark:text-zinc-400"><summary className="w-fit cursor-pointer">About these results</summary><p className="mt-1">Profit / loss excludes deposits and withdrawals and includes {money(run.fees_paid)} in fees. Return is a percentage of net contributions. Drawdown covers this review. The chart includes cash movements.</p></details>
          </div> : null}
        </section>
        <section className={`${panel} flex flex-col p-5 sm:p-6`}>
          <div className="flex items-center justify-between"><h3 className="text-sm font-semibold">Execution</h3><CapitalIcon name="activity" className="h-4 w-4 text-zinc-500 dark:text-zinc-400" /></div>
          <p role="status" className="mt-5 flex items-center gap-2 text-xs font-medium"><span aria-hidden="true" className={`h-1.5 w-1.5 rounded-full ${automatic && !staleCycle && run?.status === "running" ? "bg-emerald-500" : "bg-amber-500"}`} />{executionStatus}</p>
          <p className="mt-2 text-xs leading-5 text-zinc-500">{automatic ? "Orders are sized and executed automatically when all checks pass." : "You’re in control. Automatic entries and exits are paused."}</p>
          <dl className="my-6 grid grid-cols-2 gap-4 border-y border-zinc-100 py-4 dark:border-zinc-800">
            <div><dt className="text-[11px] text-zinc-500">Queued orders</dt><dd className="mt-1 text-2xl font-medium tabular-nums">{queued.length}</dd></div>
            <div><dt className="text-[11px] text-zinc-500">Auto exit plans</dt><dd className="mt-1 text-2xl font-medium tabular-nums">{positions.length}</dd></div>
          </dl>
          <Link href="/opportunity-queue" className="mt-auto flex items-center justify-between rounded-lg bg-zinc-900 px-3.5 py-3 text-xs font-medium text-white transition hover:bg-zinc-700 dark:bg-zinc-100 dark:text-zinc-900 dark:hover:bg-white">View opportunity queue<CapitalIcon name="arrow" /></Link>
          <p className="mt-3 text-[11px] leading-4 text-zinc-500 dark:text-zinc-400">{run ? `Last check ${when(run.last_cycle_at)}` : "Waiting for execution to start"}</p>
        </section>
      </div>
      {overview.capital ? <PortfolioDashboard dashboard={overview.capital} automatic={automatic} onTradeClosed={() => void act("refresh")} /> : null}
    </> : null}

    {overview && mode !== "dashboard" ? <p role="status" className="flex flex-wrap items-center gap-2 text-xs text-zinc-500"><CapitalIcon name="activity" />{executionStatus} · {queued.length} queued orders</p> : null}
    {overview && mode === "queue" ? <>
      <OrderTable title="Ready for automatic execution" orders={queued} kind="queue" empty={automatic ? "No executable opportunities right now. Waiting for qualifying signals, fresh quotes and risk capacity." : "Automatic trading is off. Switch to Automatic to queue and execute orders."} />
      <OrderTable title="Positions with automatic exit plans" orders={positions} kind="positions" empty="No automatic exit plans. All holdings are shown on the Capital overview." />
      {!automatic && positions.length > 0 ? <p className="text-xs text-amber-700 dark:text-amber-400">Exit plans are paused in Manual mode. Stops and targets will not execute automatically.</p> : null}
      {history.length > 0 ? <OrderTable title="Execution history" orders={history} kind="history" empty="No executions yet." /> : null}
    </> : null}
    {mode === "radar" ? <Link href="/opportunity-queue" className="inline-flex items-center gap-3 text-xs font-medium hover:underline">View execution queue<CapitalIcon name="arrow" /></Link> : null}

    {overview ? <div className="divide-y divide-zinc-200/70 border-y border-zinc-200/70 dark:divide-zinc-800 dark:border-zinc-800">
      {mode !== "radar" ? <details className="py-4">
        <summary className="cursor-pointer text-xs font-medium text-zinc-500">Automatic trading rules</summary>
        <dl className="mt-5 grid grid-cols-2 gap-x-5 gap-y-4 text-sm md:grid-cols-3">
          <Rule label="Maximum position" value={`${overview.policy.max_position_pct}% of account value`} />
          <Rule label="Planned risk per trade" value={`${overview.policy.risk_per_trade_pct}% of account value`} />
          <Rule label="Maximum positions" value={String(overview.policy.max_positions)} />
          <Rule label="Minimum cash reserve" value={`${overview.policy.cash_reserve_pct}%`} />
          <Rule label="Drawdown halt" value={`${overview.policy.max_drawdown_pct}%`} />
          <Rule label="Stop / profit target" value={`${overview.policy.stop_loss_pct}% / ${overview.policy.take_profit_pct}%`} />
        </dl>
        <p className="mt-4 text-xs leading-5 text-zinc-500">Stops trigger simulated exits; gaps can exceed the planned loss. Fees: {overview.policy.fee_bps} bps; slippage assumption: {overview.policy.slippage_bps} bps.</p>
      </details> : null}
      {overview.blockers.length ? <details className="py-4">
        <summary className="cursor-pointer text-xs font-medium text-zinc-500">Execution checks <span className="ml-1 text-zinc-500 dark:text-zinc-400">({overview.blockers.length})</span></summary>
        <ul className="mt-3 list-disc space-y-2 pl-4 text-xs leading-5 text-zinc-500">{overview.blockers.map((message, index) => <li key={`${index}-${message}`}>{message}</li>)}</ul>
      </details> : null}
      <details className="py-4 text-[11px] leading-5 text-zinc-500 dark:text-zinc-400"><summary className="cursor-pointer">About simulated execution</summary><p className="mt-2">{overview.simulation_notice}</p></details>
    </div> : null}
  </div>;
}

function Rule({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-[11px] text-zinc-500">{label}</dt><dd className="mt-1.5 text-sm font-medium tabular-nums">{value}</dd></div>;
}

function EquityChart({ history, startingCash }: { history: PaperFundOverview["equity_history"]; startingCash: string }) {
  const gradientId = useId();
  const points = history.filter((point) => Number.isFinite(Number(point.equity)) && Number.isFinite(Date.parse(point.recorded_at)));
  if (points.length < 2) return <div className="relative my-5 flex h-44 items-center justify-center overflow-hidden rounded-lg">
    <div aria-hidden="true" className="absolute inset-0 flex flex-col justify-between py-3">{[0, 1, 2, 3].map(row => <div key={row} className="border-t border-dashed border-zinc-100 dark:border-zinc-800" />)}</div>
    <div className="relative bg-white px-5 py-3 text-center dark:bg-[#111316]"><CapitalIcon name="activity" className="mx-auto mb-3 h-6 w-6 text-zinc-300 dark:text-zinc-600" /><p className="text-xs font-medium text-zinc-500">Waiting for performance data</p><p className="mt-1 text-[11px] text-zinc-500 dark:text-zinc-400">Your first two snapshots will appear here.</p></div>
  </div>;
  const start = Number(startingCash);
  const values = points.map((point) => Number(point.equity));
  const min = Math.min(start, ...values);
  const max = Math.max(start, ...values);
  const padding = Math.max((max - min) * 0.2, Math.abs(start) * 0.001, 1);
  const lower = min - padding;
  const upper = max + padding;
  const firstAt = Date.parse(points[0].recorded_at);
  const duration = Math.max(Date.parse(points[points.length - 1].recorded_at) - firstAt, 1);
  const y = (value: number) => 170 - (value - lower) / (upper - lower) * 150;
  const path = points.map((point, index) => `${index ? "L" : "M"}${10 + (Date.parse(point.recorded_at) - firstAt) / duration * 580},${y(Number(point.equity))}`).join(" ");
  const lastX = 10 + (Date.parse(points[points.length - 1].recorded_at) - firstAt) / duration * 580;
  const negative = values[values.length - 1] < start;
  return <figure className="my-5">
    <svg role="img" aria-label={`Capital account value from ${money(points[0].equity)} to ${money(points[points.length - 1].equity)}`} viewBox="0 0 600 190" className={`h-44 w-full ${negative ? "text-red-500" : "text-emerald-600 dark:text-emerald-400"}`}>
      <title>Observed Capital account value over time</title>
      <defs><linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="currentColor" stopOpacity="0.13" /><stop offset="100%" stopColor="currentColor" stopOpacity="0" /></linearGradient></defs>
      {[20, 70, 120, 170].map(row => <line key={row} x1="10" x2="590" y1={row} y2={row} className="stroke-zinc-100 dark:stroke-zinc-800" strokeDasharray="3 5" />)}
      <line x1="10" x2="590" y1={y(start)} y2={y(start)} className="stroke-zinc-300 dark:stroke-zinc-600" strokeDasharray="4 4" />
      <path d={`${path} L${lastX},180 L10,180 Z`} fill={`url(#${gradientId})`} />
      <path d={path} fill="none" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <circle cx={lastX} cy={y(values[values.length - 1])} r="3" fill="currentColor" />
    </svg>
    <figcaption className="space-y-2 text-[11px] text-zinc-500 dark:text-zinc-400"><div className="flex flex-wrap justify-between gap-2"><span>{when(points[0].recorded_at)}</span><span>{when(points[points.length - 1].recorded_at)}</span></div><p>Range {money(min)} – {money(max)} · Starting value {money(startingCash)} (dashed)</p></figcaption>
  </figure>;
}

function OrderTable({ title, orders, kind, empty }: { title: string; orders: PaperFundOrder[]; kind: "queue" | "positions" | "history"; empty: string }) {
  const cell = "whitespace-nowrap px-4 py-3 text-right tabular-nums";
  return <section className={`${panel} overflow-hidden`}>
    <h3 className="border-b border-zinc-100 px-5 py-4 text-sm font-semibold dark:border-zinc-900">{title} <span className="ml-1 text-zinc-500">({orders.length})</span></h3>
    {orders.length ? <div className="overflow-x-auto"><table className="w-full text-sm">
      <thead className="bg-zinc-50 text-xs text-zinc-500 dark:bg-zinc-900/40"><tr>
        <th scope="col" className="px-4 py-3 text-left">Instrument / status</th><th scope="col" className={cell}>Shares</th><th scope="col" className={cell}>{kind === "queue" ? "Buy limit" : "Entry"}</th><th scope="col" className={cell}>Stop</th><th scope="col" className={cell}>Target</th><th scope="col" className={cell}>{kind === "history" ? "Exit / P&L" : kind === "positions" ? "Latest mark" : "Order value (excl. fees)"}</th><th scope="col" className="px-4 py-3 text-left">{kind === "history" ? "Exit reason" : "Plan"}</th>
      </tr></thead>
      <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">{orders.map((order) => <tr key={order.id}>
        <td className="px-4 py-3"><Link href={tickerHubPath(order.ticker)} className="font-semibold hover:underline">{order.ticker}</Link><p className="mt-1 text-xs capitalize text-zinc-500">{order.status === "pending" ? "Automatic limit order" : order.status}</p></td>
        <td className={cell}>{Number(order.quantity).toLocaleString()}</td><td className={cell}>{money(kind === "queue" ? order.limit_price : order.entry_price)}</td><td className={cell}>{money(order.stop_price)}</td><td className={cell}>{money(order.target_price)}</td>
        <td className={cell}>{kind === "queue" ? money(String(Number(order.quantity) * Number(order.limit_price))) : kind === "positions" ? money(order.mark_price) : <>{money(order.exit_price)}<p className="mt-1 text-xs">{order.status === "closed" ? `P/L ${money(order.realized_pnl)}` : "Not filled"}</p></>}</td>
        <td className="min-w-56 max-w-sm px-4 py-3 text-xs leading-5 text-zinc-500">{kind === "history" ? order.exit_reason?.replaceAll("_", " ") ?? order.status : <>{order.thesis}<p className="mt-1">{kind === "queue" ? "Entry expires" : "Opened"}: {when(kind === "queue" ? order.expires_at : order.opened_at)}</p></>}</td>
      </tr>)}</tbody>
    </table></div> : <p className="px-5 py-8 text-sm leading-6 text-zinc-500">{empty}</p>}
  </section>;
}
