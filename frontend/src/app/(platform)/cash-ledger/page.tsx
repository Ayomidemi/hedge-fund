import { CashLedgerHistory } from "@/components/ledger/CashLedgerHistory";
import { getCashLedgerHistory, type CashLedgerEntry } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function CashLedgerPage() {
  let entries: CashLedgerEntry[] = [];
  let isUnavailable = false;
  const accessToken = await getServerAccessToken();

  try {
    entries = await getCashLedgerHistory({ accessToken });
  } catch {
    isUnavailable = true;
  }

  return <CashLedgerHistory entries={entries} isUnavailable={isUnavailable} />;
}
