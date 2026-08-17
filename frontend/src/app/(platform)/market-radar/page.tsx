import { MarketRadar } from "@/components/radar/MarketRadar";
import { getMarketRadarOverview, type MarketRadarOverview } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function MarketRadarPage() {
  let overview: MarketRadarOverview | null = null;
  let unavailable = false;
  const accessToken = await getServerAccessToken();

  try {
    overview = await getMarketRadarOverview("all", { accessToken });
  } catch {
    unavailable = true;
  }

  return <MarketRadar initialOverview={overview} unavailable={unavailable} />;
}
