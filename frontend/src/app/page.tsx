import { PortfolioDashboard } from "@/components/portfolio/PortfolioDashboard";
import { getOperatingCoreDashboard, type OperatingCoreDashboard } from "@/lib/api";

export default async function Home() {
  let dashboard: OperatingCoreDashboard | null = null;

  try {
    dashboard = await getOperatingCoreDashboard();
  } catch {
    dashboard = null;
  }

  return <PortfolioDashboard dashboard={dashboard} />;
}
