import { CashLedgerHistory } from "@/components/ledger/CashLedgerHistory";
import { getCashLedgerHistory, getPaperFund } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function CashLedgerPage() {
  const accessToken = await getServerAccessToken();
  const [ledger, account] = await Promise.allSettled([
    getCashLedgerHistory({ accessToken }),
    getPaperFund({ accessToken }),
  ]);

  return <CashLedgerHistory
    entries={ledger.status === "fulfilled" ? ledger.value : []}
    isUnavailable={ledger.status === "rejected"}
    overview={account.status === "fulfilled" ? account.value : null}
  />;
}
