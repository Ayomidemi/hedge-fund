import { InvestCash } from "@/components/invest/InvestCash";
import { getInvestAccount, type InvestAccount } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function InvestCashPage() {
  const accessToken = await getServerAccessToken();
  let account: InvestAccount | null = null;
  try {
    account = await getInvestAccount({ accessToken });
  } catch {
    account = null;
  }
  return <InvestCash account={account} />;
}
