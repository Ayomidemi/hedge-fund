import type { CashLedgerEntry } from "@/lib/api";

type CashLedgerHistoryProps = {
  entries: CashLedgerEntry[];
  isUnavailable?: boolean;
};

const currency = new Intl.NumberFormat("en-US", {
  style: "currency",
  currency: "USD",
});

function money(value: string) {
  return currency.format(Number(value));
}

function formatLabel(value: string) {
  return value
    .split("_")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function CashLedgerHistory({
  entries,
  isUnavailable = false,
}: CashLedgerHistoryProps) {
  const totalCash = entries.reduce((total, entry) => total + Number(entry.amount), 0);
  const deposits = entries.filter((entry) => Number(entry.amount) > 0).length;
  const withdrawals = entries.filter((entry) => Number(entry.amount) < 0).length;

  return (
    <div className="mx-auto flex max-w-[1560px] flex-col gap-5">
      {isUnavailable && (
        <div className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
          Cash ledger history unavailable. Check the backend server and refresh.
        </div>
      )}

      <section className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Cash Ledger
          </p>
          <h2 className="mt-1 text-xl font-semibold">History</h2>
        </div>
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <Summary label="Current Cash" value={currency.format(totalCash)} />
          <Summary label="Positive Entries" value={String(deposits)} />
          <Summary label="Negative Entries" value={String(withdrawals)} />
        </div>
      </section>

      <section className="overflow-hidden rounded-lg border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <div className="border-b border-zinc-200 px-4 py-3 dark:border-zinc-800">
          <p className="text-xs font-semibold uppercase tracking-wide text-zinc-500">
            Full History
          </p>
          <h3 className="text-sm font-semibold">{entries.length} Entries</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[780px] text-left text-sm">
            <thead>
              <tr>
                <Th>Date</Th>
                <Th>Type</Th>
                <Th>Description</Th>
                <Th>Reference</Th>
                <Th>Amount</Th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry) => (
                <tr key={entry.id}>
                  <Td>{entry.entry_date}</Td>
                  <Td>{formatLabel(entry.entry_type)}</Td>
                  <Td>{entry.description ?? "-"}</Td>
                  <Td>{entry.source_reference ?? "-"}</Td>
                  <Td align="right" emphasis={Number(entry.amount) !== 0}>
                    {money(entry.amount)}
                  </Td>
                </tr>
              ))}
              {entries.length === 0 && (
                <tr>
                  <td
                    colSpan={5}
                    className="px-4 py-8 text-center text-sm text-zinc-500"
                  >
                    Empty
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function Summary({ label, value }: { label: string; value: string }) {
  return (
    <div className="border-l border-zinc-200 pl-4 dark:border-zinc-800">
      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500">
        {label}
      </p>
      <p className="mt-2 text-2xl font-semibold tracking-normal">{value}</p>
    </div>
  );
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="border-b border-zinc-200 bg-zinc-50 px-4 py-2 text-xs font-medium uppercase tracking-wide text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900">
      {children}
    </th>
  );
}

function Td({
  align = "left",
  children,
  emphasis = false,
}: {
  align?: "left" | "right";
  children: React.ReactNode;
  emphasis?: boolean;
}) {
  return (
    <td
      className={`border-b border-zinc-100 px-4 py-3 text-zinc-700 dark:border-zinc-900 dark:text-zinc-300 ${
        align === "right" ? "text-right" : "text-left"
      } ${emphasis ? "font-medium text-zinc-950 dark:text-zinc-50" : ""}`}
    >
      {children}
    </td>
  );
}
