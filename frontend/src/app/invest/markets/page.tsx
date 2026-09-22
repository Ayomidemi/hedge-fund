import { InvestMarketsBoard } from "@/components/invest/InvestMarkets";
import { getInvestMarkets, type InvestMarkets } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function InvestMarketsPage() {
  const accessToken = await getServerAccessToken();
  let markets: InvestMarkets | null = null;
  try {
    markets = await getInvestMarkets({ accessToken });
  } catch {
    markets = null;
  }

  if (!markets) {
    return (
      <div className="w-full rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        Markets could not load the tape yet.
      </div>
    );
  }

  return <InvestMarketsBoard markets={markets} />;
}
