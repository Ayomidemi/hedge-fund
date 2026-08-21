"use client";

import { useMemo, useState } from "react";
import { ManualTradeModal } from "@/components/portfolio/ManualTradeModal";
import { TickerSelector } from "@/components/ticker/TickerSelector";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
  inputClassName,
} from "@/components/ui/form-styles";
import type {
  TickerSuggestion,
  TradeJournal as TradeJournalData,
  TradeJournalEntry,
} from "@/lib/api";
import {
  formatTradeMoney,
  type TickerMarket,
} from "@/lib/ticker-prefill-form";

type TradeJournalProps = {
  journal: TradeJournalData | null;
  isUnavailable: boolean;
};

const usdCurrency = new Intl.NumberFormat("en-US", {
  currency: "USD",
  style: "currency",
});

const dateFormatter = new Intl.DateTimeFormat("en-US", {
  day: "numeric",
  hour: "numeric",
  minute: "2-digit",
  month: "short",
  year: "numeric",
});

export function TradeJournal({ journal, isUnavailable }: TradeJournalProps) {
  const [modalOpen, setModalOpen] = useState(false);
  const [editingTrade, setEditingTrade] = useState<TradeJournalEntry | null>(null);
  const [tickerFilter, setTickerFilter] = useState("");
  const [tickerMarket, setTickerMarket] = useState<TickerMarket>("US");
  const [sideFilter, setSideFilter] = useState<"all" | "buy" | "sell">("all");
  const [selectedTradeId, setSelectedTradeId] = useState<string | null>(
    journal?.trades[0]?.id ?? null,
  );

  const filteredTrades = useMemo(() => {
    const ticker = tickerFilter.trim().toUpperCase();
    return (journal?.trades ?? []).filter((trade) => {
      const tickerMatches = ticker
        ? trade.instrument.ticker.includes(ticker) &&
          marketForTrade(trade) === tickerMarket
        : true;
      const sideMatches = sideFilter === "all" ? true : trade.side === sideFilter;
      return tickerMatches && sideMatches;
    });
  }, [journal?.trades, sideFilter, tickerFilter, tickerMarket]);

  const tickerSuggestions = useMemo(
    () => tradeTickerSuggestions(journal?.trades ?? []),
    [journal?.trades],
  );

  const selectedTrade =
    filteredTrades.find((trade) => trade.id === selectedTradeId) ??
    filteredTrades[0] ??
    null;

  if (!journal) {
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        {isUnavailable
          ? "Trade journal could not be loaded yet. Sign in again or refresh this page."
          : "No trade journal is available yet."}
      </div>
    );
  }

  const baseCurrency = journal.portfolio.base_currency;

  const metrics = [
    { label: "Trades", value: String(journal.summary.total_trades) },
    { label: "Tickers", value: String(journal.summary.unique_tickers) },
    { label: "Gross traded", value: money(journal.summary.gross_traded_value) },
    { label: "Net cash impact", value: money(journal.summary.net_cash_impact) },
    { label: "Fees", value: money(journal.summary.total_fees) },
  ];

  return (
    <>
      <div className="mx-auto flex max-w-[1560px] flex-col gap-5">
        <section className="rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
          <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-200 px-5 py-5 dark:border-zinc-800">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
                {journal.portfolio.name}
              </p>
              <h2 className="mt-1 text-2xl font-semibold tracking-tight">Trade Journal</h2>
            </div>
            <button
              type="button"
              onClick={() => {
                setEditingTrade(null);
                setModalOpen(true);
              }}
              className={buttonPrimaryClassName}
            >
              Record trade
            </button>
          </div>

          <div className="grid divide-y divide-zinc-200 sm:grid-cols-5 sm:divide-x sm:divide-y-0 dark:divide-zinc-800">
            {metrics.map((metric) => (
              <div key={metric.label} className="px-5 py-4">
                <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
                  {metric.label}
                </p>
                <p className="mt-2 text-xl font-semibold tabular-nums tracking-tight">
                  {metric.value}
                </p>
              </div>
            ))}
          </div>
        </section>

        <section className="grid gap-5 xl:grid-cols-[1.35fr_0.65fr]">
          <div className="overflow-hidden rounded-xl border border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
            <div className="flex flex-wrap items-end justify-between gap-3 border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
              <div>
                <h3 className="text-sm font-semibold">Executed trades</h3>
                <p className="mt-1 text-sm text-zinc-500">
                  {filteredTrades.length} of {journal.trades.length} recorded trade
                  {journal.trades.length === 1 ? "" : "s"}
                </p>
              </div>

              <div className="flex flex-wrap items-end gap-2">
                <div className="w-[360px] max-w-full">
                  <TickerSelector
                    allowTypedOption={false}
                    fetchDetailsOnSelect={false}
                    localSuggestions={tickerSuggestions}
                    market={tickerMarket}
                    marketName={null}
                    onMarketChange={setTickerMarket}
                    onTickerChange={setTickerFilter}
                    placeholder="Filter ticker"
                    tickerName={null}
                    value={tickerFilter}
                  />
                </div>
                <select
                  value={sideFilter}
                  onChange={(event) =>
                    setSideFilter(event.target.value as "all" | "buy" | "sell")
                  }
                  className={`${inputClassName} mt-0 h-10 w-32`}
                >
                  <option value="all">All sides</option>
                  <option value="buy">Buys</option>
                  <option value="sell">Sells</option>
                </select>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full min-w-[880px] text-left text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 dark:border-zinc-800">
                    <Th>Date</Th>
                    <Th>Ticker</Th>
                    <Th>CCY</Th>
                    <Th>Side</Th>
                    <Th>Quantity</Th>
                    <Th>Price</Th>
                    <Th>Notional ({baseCurrency})</Th>
                    <Th>Fees</Th>
                    <Th>Cash impact ({baseCurrency})</Th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTrades.map((trade) => {
                    const selected = trade.id === selectedTrade?.id;
                    return (
                      <tr
                        key={trade.id}
                        onClick={() => setSelectedTradeId(trade.id)}
                        className={`cursor-pointer border-b border-zinc-100 transition last:border-0 dark:border-zinc-900 ${
                          selected
                            ? "bg-zinc-100 dark:bg-zinc-900"
                            : "hover:bg-zinc-50 dark:hover:bg-zinc-900/60"
                        }`}
                      >
                        <Td>{formatDate(trade.trade_date)}</Td>
                        <Td emphasis>{trade.instrument.ticker}</Td>
                        <Td>{trade.instrument.currency}</Td>
                        <Td>
                          <SidePill side={trade.side} />
                        </Td>
                        <Td>{Number(trade.quantity).toLocaleString()}</Td>
                        <Td align="right">
                          {trade.executed_price
                            ? formatTradeMoney(
                                trade.executed_price,
                                trade.instrument.currency,
                              )
                            : "-"}
                        </Td>
                        <Td align="right">
                          {formatTradeMoney(trade.notional_value, baseCurrency)}
                        </Td>
                        <Td align="right">
                          {formatTradeMoney(trade.fees, trade.instrument.currency)}
                        </Td>
                        <Td align="right">
                          {formatTradeMoney(trade.cash_impact, baseCurrency)}
                        </Td>
                      </tr>
                    );
                  })}
                  {filteredTrades.length === 0 && (
                    <tr>
                      <td colSpan={9} className="px-5 py-10 text-center text-sm text-zinc-500">
                        No trades match this filter.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>

          <TradeDetail
            trade={selectedTrade}
            onEdit={(trade) => {
              setEditingTrade(trade);
              setModalOpen(true);
            }}
          />
        </section>
      </div>

      <ManualTradeModal
        initialTrade={editingTrade}
        open={modalOpen}
        onClose={() => {
          setModalOpen(false);
          setEditingTrade(null);
        }}
      />
    </>
  );
}

function tradeTickerSuggestions(trades: TradeJournalEntry[]): TickerSuggestion[] {
  const byTicker = new Map<string, TickerSuggestion>();
  for (const trade of trades) {
    const instrument = trade.instrument;
    if (byTicker.has(instrument.ticker)) continue;
    byTicker.set(instrument.ticker, {
      ticker: instrument.ticker,
      name: instrument.name,
      asset_class: suggestionAssetClass(instrument.asset_class),
      exchange: instrument.exchange,
      currency: instrument.currency,
      sector: instrument.sector,
      industry: instrument.industry,
    });
  }
  return Array.from(byTicker.values()).sort((left, right) =>
    left.ticker.localeCompare(right.ticker),
  );
}

function suggestionAssetClass(value: string): TickerSuggestion["asset_class"] {
  if (
    value === "equity" ||
    value === "etf" ||
    value === "bond" ||
    value === "commodity" ||
    value === "cash_equivalent" ||
    value === "other"
  ) {
    return value;
  }
  return "other";
}

function marketForTrade(trade: TradeJournalEntry): TickerMarket {
  const instrument = trade.instrument;
  const exchange = (instrument.exchange ?? "").toUpperCase();
  if (
    instrument.currency === "NGN" ||
    exchange === "NGX" ||
    exchange === "NG" ||
    instrument.ticker.endsWith(".NG")
  ) {
    return "NG";
  }
  return "US";
}

function TradeDetail({
  onEdit,
  trade,
}: {
  onEdit: (trade: TradeJournalEntry) => void;
  trade: TradeJournalEntry | null;
}) {
  if (!trade) {
    return (
      <aside className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
        <p className="text-sm text-zinc-500">Select a trade to inspect it.</p>
      </aside>
    );
  }

  return (
    <aside className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-zinc-500">
            {trade.instrument.asset_class}
          </p>
          <h3 className="mt-1 text-xl font-semibold tracking-tight">
            {trade.instrument.ticker}
          </h3>
          <p className="mt-1 text-sm text-zinc-500">
            {trade.instrument.name} · {trade.instrument.currency}
          </p>
        </div>
        <SidePill side={trade.side} />
      </div>

      <button
        type="button"
        onClick={() => onEdit(trade)}
        className={`${buttonSecondaryClassName} mt-5 w-full`}
      >
        Edit trade
      </button>

      <dl className="mt-5 grid grid-cols-2 gap-3 text-sm">
        <Metric label="Currency" value={trade.instrument.currency} />
        <Metric label="Status" value={formatLabel(trade.status)} />
        <Metric label="Exchange" value={trade.instrument.exchange || "-"} />
        <Metric
          label="Executed price"
          value={
            trade.executed_price
              ? formatTradeMoney(trade.executed_price, trade.instrument.currency)
              : "-"
          }
        />
        <Metric label="Fee bps" value={trade.fee_bps ? `${trade.fee_bps} bps` : "-"} />
        <Metric label="Broker ref" value={trade.broker_reference || "-"} />
        <Metric
          label="Risk"
          value={trade.risk_decision ? formatLabel(trade.risk_decision) : "-"}
        />
      </dl>

      <div className="mt-5 space-y-4">
        <Note title="Rationale" value={trade.rationale || "No rationale recorded."} />
        <Note title="Risk notes" value={trade.risk_notes || "No risk notes recorded."} />
        {trade.risk_override_reason ? (
          <Note title="Risk override" value={trade.risk_override_reason} />
        ) : null}
      </div>
    </aside>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-zinc-100 bg-zinc-50 p-3 dark:border-zinc-900 dark:bg-zinc-900/50">
      <dt className="text-xs font-medium uppercase tracking-wide text-zinc-500">{label}</dt>
      <dd className="mt-1 truncate font-medium">{value}</dd>
    </div>
  );
}

function Note({ title, value }: { title: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
        {title}
      </p>
      <p className="mt-1 whitespace-pre-wrap text-sm leading-6 text-zinc-700 dark:text-zinc-300">
        {value}
      </p>
    </div>
  );
}

function SidePill({ side }: { side: string }) {
  const isBuy = side === "buy";
  return (
    <span
      className={`inline-flex rounded-md px-2 py-1 text-xs font-medium ${
        isBuy
          ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300"
          : "bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300"
      }`}
    >
      {formatLabel(side)}
    </span>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="px-5 py-3 text-xs font-semibold uppercase tracking-wide text-zinc-500">
      {children}
    </th>
  );
}

function Td({
  children,
  align = "left",
  emphasis = false,
}: {
  children: React.ReactNode;
  align?: "left" | "right";
  emphasis?: boolean;
}) {
  return (
    <td
      className={`px-5 py-3 tabular-nums ${
        align === "right" ? "text-right" : "text-left"
      } ${emphasis ? "font-medium text-zinc-950 dark:text-zinc-50" : "text-zinc-600 dark:text-zinc-300"}`}
    >
      {children}
    </td>
  );
}

function money(value: string) {
  return usdCurrency.format(Number(value));
}

function formatDate(value: string) {
  return dateFormatter.format(new Date(value));
}

function formatLabel(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}
