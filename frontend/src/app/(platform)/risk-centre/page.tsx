import { RiskCentre } from "@/components/risk/RiskCentre";
import { getRiskCentreOverview, type RiskCentreOverview } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function RiskCentrePage() {
  let overview: RiskCentreOverview | null = null;
  let unavailable = false;
  const accessToken = await getServerAccessToken();

  try {
    overview = await getRiskCentreOverview({ accessToken });
  } catch {
    unavailable = true;
  }

  return <RiskCentre initialOverview={overview} unavailable={unavailable} />;
}
