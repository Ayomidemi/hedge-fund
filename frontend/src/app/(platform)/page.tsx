import { PortfolioDashboard } from "@/components/portfolio/PortfolioDashboard";
import { getOperatingCoreDashboard, type OperatingCoreDashboard } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function Home() {
  let dashboard: OperatingCoreDashboard | null = null;
  const accessToken = await getServerAccessToken();

  try {
    dashboard = await getOperatingCoreDashboard({ accessToken });
  } catch {
    dashboard = null;
  }

  return <PortfolioDashboard dashboard={dashboard} />;
}
