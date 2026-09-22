import { InvestMarketsBoard } from "@/components/invest/InvestMarkets";
import {
  getInvestConfig,
  getInvestMarkets,
  type InvestConfig,
  type InvestMarkets,
} from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function InvestMarketsPage() {
  const accessToken = await getServerAccessToken();
  let markets: InvestMarkets | null = null;
  let config: InvestConfig | null = null;
  const [marketsResult, configResult] = await Promise.allSettled([
    getInvestMarkets({ accessToken }),
    getInvestConfig({ accessToken }),
  ]);
  if (marketsResult.status === "fulfilled") {
    markets = marketsResult.value;
  }
  if (configResult.status === "fulfilled") {
    config = configResult.value;
  }

  if (!markets) {
    return (
      <div className="w-full rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        Markets could not load the tape yet.
      </div>
    );
  }

  return <InvestMarketsBoard markets={markets} searchConfig={config?.search} />;
}
