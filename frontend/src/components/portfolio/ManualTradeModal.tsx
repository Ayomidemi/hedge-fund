"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Modal } from "@/components/ui/Modal";
import { TickerCombobox } from "@/components/ticker/TickerCombobox";
import { toast } from "@/components/ui/ToastProvider";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
  inputClassName,
} from "@/components/ui/form-styles";
import {
  createManualTrade,
  getTickerPrefill,
  type TickerSuggestion,
  updateManualTrade,
  type ManualTradeInput,
  type TradeJournalEntry,
} from "@/lib/api";
import {
  instrumentFieldsFromPrefill,
  isVisiblePrefillWarning,
  normalizeTickerInput,
  shouldPrefillTicker,
  TICKER_PREFILL_DEBOUNCE_MS,
} from "@/lib/ticker-prefill-form";

type ManualTradeModalProps = {
  initialTrade?: TradeJournalEntry | null;
  open: boolean;
  onClose: () => void;
};

type InstrumentState = ManualTradeInput["instrument"];

const emptyInstrument = (): InstrumentState => ({
  ticker: "",
  name: "",
  asset_class: "equity",
  exchange: "",
  currency: "USD",
  sector: "",
  industry: "",
});

export function ManualTradeModal({
  initialTrade = null,
  open,
  onClose,
}: ManualTradeModalProps) {
  const router = useRouter();
  const [pending, setPending] = useState(false);
  const [prefillLoading, setPrefillLoading] = useState(false);
  const [prefillWarnings, setPrefillWarnings] = useState<string[]>([]);
  const [prefillProvider, setPrefillProvider] = useState<string | null>(null);
  const [market, setMarket] = useState("auto");
  const [instrument, setInstrument] = useState<InstrumentState>(emptyInstrument);
  const [side, setSide] = useState<ManualTradeInput["side"]>("buy");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [fees, setFees] = useState("0");
  const [tradeDate, setTradeDate] = useState(toDateTimeLocalValue());
  const [rationale, setRationale] = useState("");
  const [riskNotes, setRiskNotes] = useState("");
  const [brokerReference, setBrokerReference] = useState("");

  const prefillRequestId = useRef(0);
  const priceTouchedRef = useRef(false);
  const instrumentEditedRef = useRef(false);
  const openedSessionRef = useRef<string | null>(null);
  const isEditing = Boolean(initialTrade);

  // Initialise once per open session — not on every parent re-render.
  useEffect(() => {
    if (!open) {
      openedSessionRef.current = null;
      return;
    }

    const sessionKey = initialTrade?.id ?? "new";
    if (openedSessionRef.current === sessionKey) return;
    openedSessionRef.current = sessionKey;

    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;

      priceTouchedRef.current = false;
      instrumentEditedRef.current = false;
      setPrefillWarnings([]);
      setPrefillProvider(null);
      setPrefillLoading(false);

      if (initialTrade) {
        setInstrument({
          ticker: initialTrade.instrument.ticker,
          name: initialTrade.instrument.name,
          asset_class: normalizeAssetClass(initialTrade.instrument.asset_class),
          exchange: initialTrade.instrument.exchange ?? "",
          currency: initialTrade.instrument.currency,
          sector: initialTrade.instrument.sector ?? "",
          industry: initialTrade.instrument.industry ?? "",
        });
        setSide(initialTrade.side);
        setQuantity(initialTrade.quantity);
        setPrice(initialTrade.executed_price ?? "");
        priceTouchedRef.current = true;
        setFees(initialTrade.fees);
        setTradeDate(toDateTimeLocalValue(initialTrade.trade_date));
        setRationale(initialTrade.rationale);
        setRiskNotes(initialTrade.risk_notes ?? "");
        setBrokerReference(initialTrade.broker_reference ?? "");
        setMarket("auto");
        return;
      }

      setInstrument(emptyInstrument());
      setSide("buy");
      setQuantity("");
      setPrice("");
      setFees("0");
      setTradeDate(toDateTimeLocalValue());
      setRationale("");
      setRiskNotes("");
      setBrokerReference("");
      setMarket("auto");
    });

    return () => {
      cancelled = true;
    };
  }, [open, initialTrade]);

  // Debounce ticker separately — prefill only reacts to this, not other fields.
  const [debouncedTicker, setDebouncedTicker] = useState("");

  useEffect(() => {
    if (!open) return;
    const timer = window.setTimeout(() => {
      setDebouncedTicker(instrument.ticker);
    }, TICKER_PREFILL_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [instrument.ticker, open]);

  useEffect(() => {
    if (!open || isEditing) return;

    const ticker = normalizeTickerInput(debouncedTicker);
    if (!shouldPrefillTicker(ticker)) {
      return;
    }

    const requestId = ++prefillRequestId.current;

    void (async () => {
      setPrefillLoading(true);
      try {
        const result = await getTickerPrefill(
          ticker,
          market === "auto" ? undefined : market,
        );
        if (prefillRequestId.current !== requestId) return;

        const fields = instrumentFieldsFromPrefill(result);

        if (!instrumentEditedRef.current) {
          setInstrument((current) => ({
            ...current,
            ...fields,
            ticker: fields.ticker || current.ticker,
          }));
        } else {
          // User already edited details — only sync ticker normalisation + currency.
          setInstrument((current) => ({
            ...current,
            ticker: fields.ticker || current.ticker,
            currency: fields.currency,
          }));
        }

        setPrefillProvider(result.provider);
        setPrefillWarnings(
          result.source_warnings.filter(isVisiblePrefillWarning),
        );

        if (!priceTouchedRef.current && result.metrics.current_price) {
          setPrice(String(result.metrics.current_price));
        }
      } catch {
        if (prefillRequestId.current !== requestId) return;
        setPrefillProvider(null);
        setPrefillWarnings([]);
      } finally {
        if (prefillRequestId.current === requestId) {
          setPrefillLoading(false);
        }
      }
    })();
  }, [debouncedTicker, market, open, isEditing]);

  function markInstrumentEdited() {
    instrumentEditedRef.current = true;
  }

  function applyTickerSuggestion(suggestion: TickerSuggestion | null) {
    if (!suggestion) return;
    setInstrument((current) => ({
      ...current,
      ticker: suggestion.ticker,
      name: suggestion.name,
      asset_class: suggestion.asset_class,
      exchange: suggestion.exchange ?? "",
      currency: suggestion.currency,
      sector: suggestion.sector ?? "",
      industry: suggestion.industry ?? "",
    }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);

    const payload: ManualTradeInput = {
      instrument: {
        ...instrument,
        ticker: normalizeTickerInput(instrument.ticker),
        exchange: instrument.exchange || undefined,
        sector: instrument.sector || undefined,
        industry: instrument.industry || undefined,
      },
      side,
      quantity,
      price,
      fees,
      trade_date: tradeDate ? new Date(tradeDate).toISOString() : undefined,
      rationale,
      risk_notes: riskNotes || undefined,
      broker_reference: brokerReference || undefined,
    };

    try {
      if (initialTrade) {
        await updateManualTrade(initialTrade.id, payload);
        toast.success(`${payload.instrument.ticker} trade updated.`);
      } else {
        await createManualTrade(payload);
        toast.success(`${payload.instrument.ticker} trade recorded.`);
      }
      onClose();
      router.refresh();
    } catch (caught) {
      toast.error(
        caught instanceof Error
          ? caught.message
          : "Trade wasn't saved. Check the fields and try again.",
      );
    } finally {
      setPending(false);
    }
  }

  function handleClose() {
    if (pending) return;
    onClose();
  }

  return (
    <Modal
      open={open}
      onClose={handleClose}
      title={isEditing ? "Edit trade" : "Record a trade"}
      description={
        isEditing
          ? "Update the execution record. The cash movement and position book will be rebuilt from the trade ledger."
          : "Enter a ticker — instrument details and price fill in automatically after you pause typing."
      }
      size="lg"
      footer={
        <>
          <button
            type="button"
            className={buttonSecondaryClassName}
            onClick={handleClose}
            disabled={pending}
          >
            Cancel
          </button>
          <button
            type="submit"
            form="manual-trade-form"
            className={buttonPrimaryClassName}
            disabled={pending}
          >
            {pending ? "Saving..." : isEditing ? "Save changes" : "Save trade"}
          </button>
        </>
      }
    >
      <form id="manual-trade-form" onSubmit={handleSubmit} className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_120px_100px]">
          <Field label="Ticker">
            <TickerCombobox
              required
              value={instrument.ticker}
              onChange={(ticker) =>
                setInstrument((current) => ({
                  ...current,
                  ticker,
                }))
              }
              onSelect={applyTickerSuggestion}
              className={inputClassName}
              placeholder="e.g. AAPL or SEPLAT"
            />
          </Field>
          <Field label="Market">
            <select
              value={market}
              onChange={(event) => setMarket(event.target.value)}
              className={inputClassName}
              disabled={isEditing}
            >
              <option value="auto">Auto</option>
              <option value="US">US</option>
              <option value="NG">Nigeria</option>
            </select>
          </Field>
          <Field label="Currency">
            <input
              readOnly
              value={instrument.currency}
              className={`${inputClassName} bg-zinc-50 dark:bg-zinc-900`}
              title="Set automatically from ticker prefill"
            />
          </Field>
        </div>

        {prefillProvider ? (
          <p className="text-xs text-zinc-500">
            Instrument details from {prefillProvider}
            {instrument.currency !== "USD" ? ` · ${instrument.currency} listing` : ""}
          </p>
        ) : prefillLoading ? (
          <p className="text-xs text-zinc-500">Prefilling instrument details...</p>
        ) : null}

        {prefillWarnings.length > 0 ? (
          <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200">
            {prefillWarnings.map((warning) => (
              <p key={warning}>{warning}</p>
            ))}
          </div>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name">
            <input
              required
              value={instrument.name}
              onChange={(event) => {
                markInstrumentEdited();
                setInstrument((current) => ({ ...current, name: event.target.value }));
              }}
              className={inputClassName}
            />
          </Field>
          <Field label="Asset class">
            <select
              value={instrument.asset_class}
              onChange={(event) => {
                markInstrumentEdited();
                setInstrument((current) => ({
                  ...current,
                  asset_class: event.target.value as InstrumentState["asset_class"],
                }));
              }}
              className={inputClassName}
            >
              <option value="equity">Equity</option>
              <option value="etf">ETF</option>
              <option value="bond">Bond</option>
              <option value="commodity">Commodity</option>
              <option value="cash_equivalent">Cash equivalent</option>
              <option value="other">Other</option>
            </select>
          </Field>
          <Field label="Side">
            <select
              value={side}
              onChange={(event) => setSide(event.target.value as ManualTradeInput["side"])}
              className={inputClassName}
            >
              <option value="buy">Buy</option>
              <option value="sell">Sell</option>
            </select>
          </Field>
          <Field label="Quantity">
            <input
              type="number"
              step="0.00000001"
              required
              value={quantity}
              onChange={(event) => setQuantity(event.target.value)}
              className={inputClassName}
            />
          </Field>
          <Field label={`Price (${instrument.currency})`}>
            <input
              type="number"
              step="0.000001"
              required
              value={price}
              onChange={(event) => {
                priceTouchedRef.current = true;
                setPrice(event.target.value);
              }}
              className={inputClassName}
            />
          </Field>
          <Field label={`Fees (${instrument.currency})`}>
            <input
              type="number"
              step="0.01"
              value={fees}
              onChange={(event) => setFees(event.target.value)}
              className={inputClassName}
            />
          </Field>
          <Field label="Sector">
            <input
              value={instrument.sector}
              onChange={(event) => {
                markInstrumentEdited();
                setInstrument((current) => ({ ...current, sector: event.target.value }));
              }}
              className={inputClassName}
            />
          </Field>
          <Field label="Exchange">
            <input
              value={instrument.exchange}
              onChange={(event) => {
                markInstrumentEdited();
                setInstrument((current) => ({ ...current, exchange: event.target.value }));
              }}
              className={inputClassName}
            />
          </Field>
          <Field label="Industry">
            <input
              value={instrument.industry}
              onChange={(event) => {
                markInstrumentEdited();
                setInstrument((current) => ({ ...current, industry: event.target.value }));
              }}
              className={inputClassName}
            />
          </Field>
          <Field label="Trade date">
            <input
              type="datetime-local"
              required
              value={tradeDate}
              onChange={(event) => setTradeDate(event.target.value)}
              className={inputClassName}
            />
          </Field>
          <Field label="Broker reference">
            <input
              value={brokerReference}
              onChange={(event) => setBrokerReference(event.target.value)}
              className={inputClassName}
            />
          </Field>
        </div>

        <Field label="Rationale">
          <textarea
            required
            rows={3}
            value={rationale}
            onChange={(event) => setRationale(event.target.value)}
            className={inputClassName}
          />
        </Field>

        <Field label="Risk notes">
          <textarea
            rows={2}
            value={riskNotes}
            onChange={(event) => setRiskNotes(event.target.value)}
            className={inputClassName}
          />
        </Field>
      </form>
    </Modal>
  );
}

function toDateTimeLocalValue(value?: string) {
  const date = value ? new Date(value) : new Date();
  const offsetMs = date.getTimezoneOffset() * 60 * 1000;
  return new Date(date.getTime() - offsetMs).toISOString().slice(0, 16);
}

function normalizeAssetClass(value: string): InstrumentState["asset_class"] {
  if (
    value === "etf" ||
    value === "bond" ||
    value === "commodity" ||
    value === "cash_equivalent" ||
    value === "other"
  ) {
    return value;
  }
  return "equity";
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="block text-sm font-medium text-zinc-700 dark:text-zinc-300">
      {label}
      {children}
    </label>
  );
}
