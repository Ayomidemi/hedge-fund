import { AttributionDashboard } from "@/components/attribution/AttributionDashboard";
import { getAttributionReport, type AttributionReport } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function AttributionPage() {
  let report: AttributionReport | null = null;
  let unavailable = false;
  const accessToken = await getServerAccessToken();

  try {
    report = await getAttributionReport({ accessToken });
  } catch {
    unavailable = true;
  }

  return <AttributionDashboard report={report} isUnavailable={unavailable} />;
}
