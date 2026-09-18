import { InvestCash } from "@/components/invest/InvestCash";
import {
  getInvestAccount,
  getInvestTransactions,
  type InvestAccount,
  type InvestTransaction,
} from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function InvestCashPage() {
  const accessToken = await getServerAccessToken();
  let account: InvestAccount | null = null;
  let transactions: InvestTransaction[] = [];
  try {
    account = await getInvestAccount({ accessToken });
    transactions = await getInvestTransactions({ accessToken });
  } catch {
    account = null;
    transactions = [];
  }
  return <InvestCash account={account} transactions={transactions} />;
}
