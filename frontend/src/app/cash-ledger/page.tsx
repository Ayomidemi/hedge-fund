import { CashLedgerHistory } from "@/components/ledger/CashLedgerHistory";
import { getCashLedgerHistory, type CashLedgerEntry } from "@/lib/api";

export default async function CashLedgerPage() {
  let entries: CashLedgerEntry[] = [];
  let isUnavailable = false;

  try {
    entries = await getCashLedgerHistory();
  } catch {
    isUnavailable = true;
  }

  return <CashLedgerHistory entries={entries} isUnavailable={isUnavailable} />;
}
