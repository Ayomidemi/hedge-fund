"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  getPaperFund,
  setPaperFundPaused,
  startPaperFund,
  type PaperFundOrder,
  type PaperFundOverview,
} from "@/lib/api";
import { newIdempotencyKey } from "@/lib/idempotency";
import { tickerHubPath } from "@/lib/ticker-hub-path";
import { buttonPrimaryClassName, buttonSecondaryClassName } from "@/components/ui/form-styles";
import { toast } from "@/components/ui/ToastProvider";

const usd = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
const timestamps = new Intl.DateTimeFormat("en-US", {
  month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short",
});
const panel = "rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950";

function money(value: string | null) {
  return value !== null && Number.isFinite(Number(value)) ? usd.format(Number(value)) : "—";
}

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
  const startKey = useRef<string | null>(null);
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
            : "The paper fund is unavailable. Retry to load balances and trading controls.");
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

  async function act(action: "refresh" | "start" | "pause" | "resume") {
    if (actionInFlight.current) return;
    actionInFlight.current = true;
    const version = ++requestVersion.current;
    setPending(true);
    setError(null);
    try {
      if (action === "start" && !startKey.current) startKey.current = newIdempotencyKey();
      const data = action === "start"
        ? await startPaperFund({ idempotencyKey: startKey.current! })
        : action === "refresh"
          ? await getPaperFund()
          : await setPaperFundPaused(action === "pause");
      if (version === requestVersion.current) {
        hasSnapshot.current = true;
        setOverview(data);
      }
      if (action === "start") startKey.current = null;
      if (action !== "refresh") {
        toast.success(action === "start" ? "$10,000 paper fund started." : action === "pause" ? "New entries paused. Automatic exits remain active." : "Automatic entries resumed.");
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Paper fund request failed.");
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
  const status = overview ? run?.status ?? "not started" : loading ? "loading" : "unavailable";
  const canStart = overview && (!run || run.status === "completed");
  const staleCycle = Boolean(run && run.status !== "completed" && run.last_cycle_at && overview
    && Date.parse(overview.generated_at) - Date.parse(run.last_cycle_at) > 90_000);

  return (
    <div className="space-y-5">
      <section className={panel} aria-label="Automatic paper fund">
        <div className="flex flex-wrap items-start justify-between gap-4 p-5 sm:p-6">
          <div className="max-w-2xl">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-emerald-700 dark:text-emerald-400">Paper trading · USD · Weekly review</p>
            <h2 className="mt-1 text-2xl font-semibold tracking-tight">
              {mode === "queue" ? "Opportunity Queue" : "$10,000 automatic paper fund"}
            </h2>
            <p className="mt-2 text-sm leading-6 text-zinc-500">
              {mode === "queue"
                ? "Only sized limit orders accepted by the engine enter this queue. Entries, stops, targets, and time exits are automatic."
                : "The system screens radar signals, sizes positions, and manages entry and exit orders. Track the actual simulated gain or loss over one week."}
            </p>
            <p className="mt-2 text-xs text-zinc-500">The paper fund has its own cash and positions. Each trading period lasts seven days.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-zinc-100 px-3 py-1.5 text-xs font-medium capitalize dark:bg-zinc-900">{status}</span>
            {canStart ? <button disabled={pending} onClick={() => void act("start")} className={buttonPrimaryClassName}>
              {pending ? "Starting…" : run ? "Start next $10,000 trading period" : "Start $10,000 paper fund"}
            </button> : null}
            {run?.status === "running" || run?.status === "paused" ? <button disabled={pending} onClick={() => void act(run.status === "running" ? "pause" : "resume")} className={buttonSecondaryClassName}>
              {run.status === "running" ? "Pause new entries" : "Resume new entries"}
            </button> : null}
            <button disabled={pending} onClick={() => void act("refresh")} className={buttonSecondaryClassName} aria-label="Refresh paper fund">{pending ? "Updating…" : error ? "Retry" : "Refresh"}</button>
          </div>
        </div>

        {error ? <p role="alert" className="mx-5 mb-5 rounded-lg bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">{error}</p> : null}
        {loading ? <p role="status" className="mx-5 mb-5 text-sm text-zinc-500">Loading paper fund balances and trading controls…</p> : null}

        {run ? <>
          <div className="grid gap-3 px-5 pb-5 sm:grid-cols-2 sm:px-6 xl:grid-cols-4">
            <Metric label="Paper equity" value={money(run.equity)} detail={`Started with ${money(run.starting_cash)}`} />
            <Metric label="Net profit / loss" value={money(run.total_pnl)} detail={`${Number(run.return_pct).toFixed(2)}% return · after simulated fees`} tone={Number(run.total_pnl) < 0 ? "negative" : Number(run.total_pnl) > 0 ? "positive" : undefined} />
            <Metric label="Available cash" value={money(run.available_cash)} detail={`${money(run.reserved_cash)} reserved for orders`} />
            <Metric label="Maximum drawdown" value={`${Number(run.max_drawdown_pct).toFixed(2)}%`} detail={`${queued.length} queued · ${positions.length} open positions`} />
          </div>
          <div className="flex flex-wrap justify-between gap-2 border-t border-zinc-100 px-5 py-3 text-xs text-zinc-500 dark:border-zinc-900 sm:px-6">
            <span>Started {when(run.started_at)} · Trading period ends {when(run.ends_at)}</span>
            <span>Last engine cycle: {when(run.last_cycle_at)}</span>
          </div>
          {staleCycle ? <p className="mx-5 mb-4 text-sm text-amber-700 dark:text-amber-400">The engine has not reported a cycle for over 90 seconds. Automatic execution may be delayed.</p> : null}
          {run.halt_reason ? <p role="status" className="mx-5 mb-4 rounded-lg bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">{run.halt_reason}</p> : null}
          {run.status === "paused" ? <p className="mx-5 mb-4 text-sm text-zinc-500">New buys are paused. Existing positions retain their automatic exits.</p> : null}
          {run.status === "liquidating" ? <p className="mx-5 mb-4 text-sm text-zinc-500">The paper fund is closing positions when eligible market quotes are available. Final profit or loss remains provisional until every position closes.</p> : null}
        </> : null}

        {mode === "radar" ? <div className="border-t border-zinc-100 px-5 py-4 dark:border-zinc-900">
          <Link href="/opportunity-queue" className="text-sm font-medium text-emerald-700 hover:underline dark:text-emerald-400">{overview ? `View ${queued.length} automatically queued order${queued.length === 1 ? "" : "s"}` : "View automatic execution queue"} →</Link>
        </div> : null}
      </section>

      {overview && mode !== "radar" ? <>
        <div className="grid gap-5 lg:grid-cols-2">
          <section className={`${panel} p-5`}>
            <h3 className="text-sm font-semibold">{run?.status === "completed" ? "Weekly review" : "Week-to-date performance"}</h3>
            {run ? <>
              <EquityChart history={overview.equity_history} startingCash={run.starting_cash} />
              <dl className="grid grid-cols-3 gap-3 text-sm">
                <div><dt className="text-xs text-zinc-500">Realized P&amp;L</dt><dd className="mt-1 tabular-nums">{money(run.realized_pnl)}</dd></div>
                <div><dt className="text-xs text-zinc-500">Unrealized P&amp;L</dt><dd className="mt-1 tabular-nums">{money(run.unrealized_pnl)}</dd></div>
                <div><dt className="text-xs text-zinc-500">Simulated fees</dt><dd className="mt-1 tabular-nums">{money(run.fees_paid)}</dd></div>
              </dl>
            </> : <p className="mt-3 text-sm leading-6 text-zinc-500">Start the paper fund to establish a $10,000 baseline. The weekly review will reflect observed fills and market moves; there is no projected profit.</p>}
          </section>
          <section className={`${panel} p-5`}>
            <h3 className="text-sm font-semibold">Capital rules</h3>
            <dl className="mt-4 grid grid-cols-2 gap-x-5 gap-y-3 text-sm">
              <Rule label="Maximum position" value={`${overview.policy.max_position_pct}% of equity`} />
              <Rule label="Planned risk per trade" value={`${overview.policy.risk_per_trade_pct}% of equity`} />
              <Rule label="Maximum positions" value={String(overview.policy.max_positions)} />
              <Rule label="Minimum cash reserve" value={`${overview.policy.cash_reserve_pct}%`} />
              <Rule label="Drawdown halt" value={`${overview.policy.max_drawdown_pct}%`} />
              <Rule label="Stop / profit target" value={`${overview.policy.stop_loss_pct}% / ${overview.policy.take_profit_pct}%`} />
            </dl>
            <p className="mt-4 text-xs leading-5 text-zinc-500">Stops trigger simulated exits; gaps can exceed the planned loss. Fees: {overview.policy.fee_bps} bps; slippage assumption: {overview.policy.slippage_bps} bps.</p>
          </section>
        </div>

        <OrderTable title="Ready for automatic execution" orders={queued} kind="queue" empty="No executable opportunities right now. The engine waits for qualifying signals, fresh quotes, and available risk capacity." />
        {mode === "queue" || positions.length > 0 ? <OrderTable title="Open paper positions" orders={positions} kind="positions" empty="No open paper positions." /> : null}
        {mode === "queue" && history.length > 0 ? <OrderTable title="Execution history" orders={history} kind="history" empty="No executions yet." /> : null}
        {mode === "dashboard" ? <Link href="/opportunity-queue" className="inline-block text-sm font-medium text-emerald-700 hover:underline dark:text-emerald-400">View orders, positions, and execution history →</Link> : null}
      </> : null}

      {overview?.blockers.length ? <section className={`${panel} p-5`}>
        <h3 className="text-sm font-semibold">Execution checks</h3>
        <ul className="mt-2 list-disc space-y-1 pl-4 text-sm text-zinc-500">{overview.blockers.map((message, index) => <li key={`${index}-${message}`}>{message}</li>)}</ul>
      </section> : null}
      {overview ? <p className="text-xs leading-5 text-zinc-500">{overview.simulation_notice} Snapshot: {when(overview.generated_at)}.</p> : null}
    </div>
  );
}

function Metric({ label, value, detail, tone }: { label: string; value: string; detail: string; tone?: "positive" | "negative" }) {
  return <div className="rounded-lg bg-zinc-50 p-4 dark:bg-zinc-900/50">
    <p className="text-xs text-zinc-500">{label}</p>
    <p className={`mt-2 text-2xl font-semibold tabular-nums ${tone === "positive" ? "text-emerald-700 dark:text-emerald-400" : tone === "negative" ? "text-red-700 dark:text-red-400" : ""}`}>{value}</p>
    <p className="mt-1 text-xs text-zinc-500">{detail}</p>
  </div>;
}

function Rule({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-xs text-zinc-500">{label}</dt><dd className="mt-1 font-medium">{value}</dd></div>;
}

function EquityChart({ history, startingCash }: { history: PaperFundOverview["equity_history"]; startingCash: string }) {
  const points = history.filter((point) => Number.isFinite(Number(point.equity)) && Number.isFinite(Date.parse(point.recorded_at)));
  if (points.length < 2) return <p className="my-6 text-sm text-zinc-500">Equity history will appear as the engine records snapshots.</p>;
  const start = Number(startingCash);
  const values = points.map((point) => Number(point.equity));
  const min = Math.min(start, ...values);
  const max = Math.max(start, ...values);
  const span = max - min || Math.max(start * 0.01, 1);
  const firstAt = Date.parse(points[0].recorded_at);
  const duration = Math.max(Date.parse(points[points.length - 1].recorded_at) - firstAt, 1);
  const y = (value: number) => 130 - (value - min) / span * 100;
  const path = points.map((point, index) => `${index ? "L" : "M"}${10 + (Date.parse(point.recorded_at) - firstAt) / duration * 480},${y(Number(point.equity))}`).join(" ");
  return <figure className="my-4">
    <svg role="img" aria-label={`Paper equity from ${money(points[0].equity)} to ${money(points[points.length - 1].equity)}`} viewBox="0 0 500 155" className="h-40 w-full">
      <title>Observed paper equity over time</title>
      <line x1="10" x2="490" y1={y(start)} y2={y(start)} className="stroke-zinc-300 dark:stroke-zinc-700" strokeDasharray="4 4" />
      <path d={path} fill="none" strokeWidth="2.5" className={values[values.length - 1] < start ? "stroke-red-500" : "stroke-emerald-500"} />
    </svg>
    <figcaption className="flex justify-between gap-3 text-xs text-zinc-500"><span>{when(points[0].recorded_at)}</span><span>Dashed line: {money(startingCash)} baseline</span></figcaption>
  </figure>;
}

function OrderTable({ title, orders, kind, empty }: { title: string; orders: PaperFundOrder[]; kind: "queue" | "positions" | "history"; empty: string }) {
  const cell = "whitespace-nowrap px-4 py-3 text-right tabular-nums";
  return <section className={`${panel} overflow-hidden`}>
    <h3 className="border-b border-zinc-100 px-5 py-4 text-sm font-semibold dark:border-zinc-900">{title} <span className="ml-1 text-zinc-500">({orders.length})</span></h3>
    {orders.length ? <div className="overflow-x-auto"><table className="w-full text-sm">
      <thead className="bg-zinc-50 text-xs text-zinc-500 dark:bg-zinc-900/40"><tr>
        <th scope="col" className="px-4 py-3 text-left">Instrument / status</th><th scope="col" className={cell}>Shares</th><th scope="col" className={cell}>{kind === "queue" ? "Buy limit" : "Entry"}</th><th scope="col" className={cell}>Stop</th><th scope="col" className={cell}>Target</th><th scope="col" className={cell}>{kind === "history" ? "Exit / P&L" : kind === "positions" ? "Latest mark" : "Reserved notional"}</th><th scope="col" className="px-4 py-3 text-left">{kind === "history" ? "Exit reason" : "Plan"}</th>
      </tr></thead>
      <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">{orders.map((order) => <tr key={order.id}>
        <td className="px-4 py-3"><Link href={tickerHubPath(order.ticker)} className="font-semibold hover:underline">{order.ticker}</Link><p className="mt-1 text-xs capitalize text-zinc-500">{order.status === "pending" ? "Automatic limit order" : order.status}</p></td>
        <td className={cell}>{Number(order.quantity).toLocaleString()}</td><td className={cell}>{money(kind === "queue" ? order.limit_price : order.entry_price)}</td><td className={cell}>{money(order.stop_price)}</td><td className={cell}>{money(order.target_price)}</td>
        <td className={cell}>{kind === "queue" ? money(String(Number(order.quantity) * Number(order.limit_price))) : kind === "positions" ? money(order.mark_price) : <>{money(order.exit_price)}<p className="mt-1 text-xs">P&amp;L {money(order.realized_pnl)}</p></>}</td>
        <td className="min-w-56 max-w-sm px-4 py-3 text-xs leading-5 text-zinc-500">{kind === "history" ? order.exit_reason?.replaceAll("_", " ") ?? order.status : <>{order.thesis}<p className="mt-1">{kind === "queue" ? "Entry expires" : "Opened"}: {when(kind === "queue" ? order.expires_at : order.opened_at)}</p></>}</td>
      </tr>)}</tbody>
    </table></div> : <p className="px-5 py-8 text-sm leading-6 text-zinc-500">{empty}</p>}
  </section>;
}
