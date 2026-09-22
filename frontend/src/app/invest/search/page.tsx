import { InvestSearch } from "@/components/invest/InvestSearch";
import { getInvestConfig, type InvestConfig } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function InvestSearchPage() {
  const accessToken = await getServerAccessToken();
  let config: InvestConfig | null = null;
  try {
    config = await getInvestConfig({ accessToken });
  } catch {
    config = null;
  }

  return (
    <InvestSearch
      initialQuery={config?.search.default_query}
      initialMarket={config?.search.default_market}
      markets={config?.search.markets}
    />
  );
}
