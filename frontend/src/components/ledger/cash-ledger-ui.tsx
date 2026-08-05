const entryTypeLabels: Record<string, string> = {
  deposit: "Deposit",
  withdrawal: "Withdrawal",
  adjustment: "Adjustment",
  initial_capital: "Initial capital",
  trade_buy: "Trade buy",
  trade_sell: "Trade sell",
};

const platformLabels: Record<string, string> = {
  alpaca: "Alpaca",
  bamboo: "Bamboo",
  interactive_brokers: "Interactive Brokers",
  robinhood: "Robinhood",
  fidelity: "Fidelity",
  schwab: "Schwab",
  manual: "Manual",
};

export const cashPlatformSuggestions = [
  "Alpaca",
  "Bamboo",
  "Interactive Brokers",
  "Robinhood",
  "Fidelity",
  "Schwab",
  "Manual",
] as const;

function formatLabel(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function CashLedgerTypeBadge({ type }: { type: string }) {
  const label = entryTypeLabels[type] ?? formatLabel(type);

  return (
    <span className="inline-flex rounded-md border border-zinc-200 bg-white px-2 py-0.5 text-xs font-medium text-zinc-700 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-300">
      {label}
    </span>
  );
}

export function formatPlatformLabel(platform: string | undefined | null) {
  if (!platform) {
    return "Manual";
  }

  const normalized = platform.trim().toLowerCase().replace(/\s+/g, "_");
  return platformLabels[normalized] ?? platform.trim();
}

export function formatSignedAmount(value: string) {
  const amount = Number(value);
  const formatted = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
  }).format(Math.abs(amount));

  if (amount > 0) return `+${formatted}`;
  if (amount < 0) return `−${formatted}`;
  return formatted;
}

export const cashEntryDescriptions = {
  deposit: "Bring capital into the fund — funding, top-ups, or inbound transfers.",
  withdrawal: "Move capital out — draws, outbound transfers, or distributions.",
  adjustment:
    "Fix the books — reconciliation corrections, fees, or other non-trade cash events.",
} as const;
