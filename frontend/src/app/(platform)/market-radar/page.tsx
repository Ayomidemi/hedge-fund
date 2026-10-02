import { MarketRadar } from "@/components/radar/MarketRadar";
import { PaperFundPanel } from "@/components/portfolio/PaperFundPanel";
import { getMarketRadarOverview, getPaperFund } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function MarketRadarPage() {
  const accessToken = await getServerAccessToken();
  const [overview, paperFund] = await Promise.allSettled([
    getMarketRadarOverview("all", { accessToken }),
    getPaperFund({ accessToken }),
  ]);
  return (
    <div className="mx-auto max-w-[1400px] space-y-6">
      <PaperFundPanel initialOverview={paperFund.status === "fulfilled" ? paperFund.value : null} mode="radar" />
      <MarketRadar initialOverview={overview.status === "fulfilled" ? overview.value : null} unavailable={overview.status === "rejected"} />
    </div>
  );
}
