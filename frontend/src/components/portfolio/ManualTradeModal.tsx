"use client";

import { FormEvent, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Modal } from "@/components/ui/Modal";
import { TickerSelector } from "@/components/ticker/TickerSelector";
import { toast } from "@/components/ui/ToastProvider";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
  inputClassName,
} from "@/components/ui/form-styles";
import {
  createManualTrade,
  createPreTradeRiskCheck,
  type PreTradeRiskCheck,
  type PreTradeRiskInput,
  type TickerPrefill,
  type TickerSuggestion,
  updateManualTrade,
  type ManualTradeInput,
  type TradeJournalEntry,
} from "@/lib/api";
import {
  instrumentFieldsFromPrefill,
  isVisiblePrefillWarning,
  marketFromTickerSuggestion,
  normalizeTickerInput,
  type TickerMarket,
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
  const [market, setMarket] = useState<TickerMarket>("US");
  const [instrument, setInstrument] = useState<InstrumentState>(emptyInstrument);
  const [side, setSide] = useState<ManualTradeInput["side"]>("buy");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [fees, setFees] = useState("0");
  const [tradeDate, setTradeDate] = useState(toDateTimeLocalValue());
  const [rationale, setRationale] = useState("");
  const [riskNotes, setRiskNotes] = useState("");
  const [preTradeCheck, setPreTradeCheck] = useState<PreTradeRiskCheck | null>(null);
  const [preTradeSignature, setPreTradeSignature] = useState<string | null>(null);
  const [riskOverrideReason, setRiskOverrideReason] = useState("");
  const [brokerReference, setBrokerReference] = useState("");

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
      setPreTradeCheck(null);
      setPreTradeSignature(null);
      setRiskOverrideReason("");

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
        setRiskOverrideReason(initialTrade.risk_override_reason ?? "");
        setBrokerReference(initialTrade.broker_reference ?? "");
        setMarket(marketFromInstrument(initialTrade.instrument));
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
      setRiskOverrideReason("");
      setBrokerReference("");
      setMarket("US");
    });

    return () => {
      cancelled = true;
    };
  }, [open, initialTrade]);

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
    setMarket(marketFromTickerSuggestion(suggestion));
  }

  function applyTickerDetails(prefill: TickerPrefill | null) {
    if (!prefill) {
      setPrefillProvider(null);
      setPrefillWarnings([]);
      return;
    }

    const fields = instrumentFieldsFromPrefill(prefill);
    if (!instrumentEditedRef.current) {
      setInstrument((current) => ({
        ...current,
        ...fields,
        ticker: fields.ticker || current.ticker,
      }));
    } else {
      setInstrument((current) => ({
        ...current,
        ticker: fields.ticker || current.ticker,
        currency: fields.currency,
      }));
    }

    setPrefillProvider(prefill.provider);
    setPrefillWarnings(prefill.source_warnings.filter(isVisiblePrefillWarning));

    if (!priceTouchedRef.current && prefill.metrics.current_price) {
      setPrice(String(prefill.metrics.current_price));
    }
  }

  function buildPayload(): ManualTradeInput {
    return {
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
      rationale: rationale.trim() || undefined,
      risk_notes: riskNotes || undefined,
      broker_reference: brokerReference || undefined,
    };
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);

    const payload = buildPayload();

    try {
      if (initialTrade) {
        await updateManualTrade(initialTrade.id, payload);
        toast.success(`${payload.instrument.ticker} trade updated.`);
      } else {
        const signature = manualTradeRiskSignature(payload);
        let riskCheck = preTradeCheck;
        if (!riskCheck || preTradeSignature !== signature) {
          riskCheck = await createPreTradeRiskCheck(toPreTradeRiskInput(payload));
          setPreTradeCheck(riskCheck);
          setPreTradeSignature(signature);
        }

        if (riskCheck.decision === "reject") {
          toast.error("Risk rejected this trade. Adjust the order before saving.");
          return;
        }

        const overrideReason = riskOverrideReason.trim();
        if (riskCheck.decision !== "approve" && !overrideReason) {
          toast.error("Risk review requires an override reason before saving.");
          return;
        }

        await createManualTrade({
          ...payload,
          pre_trade_check_id: riskCheck.id,
          risk_override_reason:
            riskCheck.decision === "approve" ? undefined : overrideReason || undefined,
        });
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
          : "Choose the country first, then select a ticker. Instrument details and price fill in from that selection."
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
        <div className="grid gap-4 sm:grid-cols-[minmax(0,1fr)_100px]">
          <TickerSelector
            required
            disabled={isEditing}
            market={market}
            value={instrument.ticker}
            onMarketChange={setMarket}
            onTickerChange={(ticker) =>
              setInstrument((current) => ({
                ...current,
                ticker,
              }))
            }
            onSuggestion={applyTickerSuggestion}
            onDetails={applyTickerDetails}
            onLoadingChange={setPrefillLoading}
            className={inputClassName}
            placeholder="e.g. AAPL or SEPLAT"
          />
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

        {!isEditing && preTradeCheck ? (
          <RiskDecisionNotice
            check={preTradeCheck}
            isCurrent={preTradeSignature === manualTradeRiskSignature(buildPayload())}
          />
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

        {!isEditing && preTradeCheck && preTradeCheck.decision !== "approve" && preTradeCheck.decision !== "reject" ? (
          <Field label="Risk override reason">
            <textarea
              rows={2}
              value={riskOverrideReason}
              onChange={(event) => setRiskOverrideReason(event.target.value)}
              className={inputClassName}
              required
            />
          </Field>
        ) : null}
      </form>
    </Modal>
  );
}

function RiskDecisionNotice({
  check,
  isCurrent,
}: {
  check: PreTradeRiskCheck;
  isCurrent: boolean;
}) {
  const tone =
    check.decision === "approve"
      ? "border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200"
      : check.decision === "reject"
        ? "border-red-200 bg-red-50 text-red-900 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200"
        : "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900 dark:bg-amber-950/40 dark:text-amber-200";

  return (
    <div className={`rounded-lg border px-3 py-2 text-xs ${tone}`}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="font-semibold">
          Risk: {formatRiskLabel(check.decision)} · {formatRiskLabel(check.risk_level)}
        </p>
        {!isCurrent ? <span>Form changed since this check</span> : null}
      </div>
      {check.messages.length > 0 ? (
        <div className="mt-1 space-y-1">
          {check.messages.map((message) => (
            <p key={message}>{message}</p>
          ))}
        </div>
      ) : null}
    </div>
  );
}

function toPreTradeRiskInput(payload: ManualTradeInput): PreTradeRiskInput {
  return {
    instrument: payload.instrument,
    side: payload.side,
    quantity: payload.quantity,
    price: payload.price,
    fees: payload.fees,
    trade_date: payload.trade_date,
    rationale: payload.rationale,
  };
}

function manualTradeRiskSignature(payload: ManualTradeInput) {
  return JSON.stringify({
    instrument: {
      ticker: payload.instrument.ticker,
      name: payload.instrument.name,
      asset_class: payload.instrument.asset_class,
      exchange: payload.instrument.exchange ?? null,
      currency: payload.instrument.currency,
      sector: payload.instrument.sector ?? null,
      industry: payload.instrument.industry ?? null,
    },
    side: payload.side,
    quantity: payload.quantity,
    price: payload.price,
    fees: payload.fees,
  });
}

function formatRiskLabel(value: string) {
  return value
    .split(/[-_\s]+/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
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

function marketFromInstrument(instrument: TradeJournalEntry["instrument"]): TickerMarket {
  const exchange = (instrument.exchange ?? "").trim().toUpperCase();
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
