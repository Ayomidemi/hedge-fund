import { StrategyPods } from "@/components/strategy/StrategyPods";
import { getStrategyPods, type StrategyPodsOverview } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function StrategyPodsPage() {
  let overview: StrategyPodsOverview | null = null;
  let unavailable = false;
  const accessToken = await getServerAccessToken();

  try {
    overview = await getStrategyPods({ accessToken });
  } catch {
    unavailable = true;
  }

  return <StrategyPods initialOverview={overview} unavailable={unavailable} />;
}
