export function money(
  value: string | number | null | undefined,
  currency = "USD",
) {
  if (value === null || value === undefined || value === "" || !Number.isFinite(Number(value))) return "—";
  const amount = Number(value);
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 2,
  }).format(amount);
}

export function signedMoney(value: string | number | null | undefined, currency = "USD") {
  if (value === null || value === undefined || value === "" || !Number.isFinite(Number(value))) return "—";
  const amount = Number(value);
  const formatted = money(Math.abs(amount), currency);
  if (amount > 0) return `+${formatted}`;
  if (amount < 0) return `-${formatted}`;
  return formatted;
}

export function signedPercent(value: string | number | null | undefined) {
  if (value === null || value === undefined || value === "") return "—";
  const amount = Number(value);
  if (!Number.isFinite(amount)) return "—";
  const formatted = `${Math.abs(amount).toFixed(2)}%`;
  if (amount > 0) return `+${formatted}`;
  if (amount < 0) return `-${formatted}`;
  return formatted;
}
