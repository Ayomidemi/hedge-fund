import { PaperFundPanel } from "@/components/portfolio/PaperFundPanel";
import { PortfolioDashboard } from "@/components/portfolio/PortfolioDashboard";
import { getOperatingCoreDashboard, getPaperFund } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function Home() {
  const accessToken = await getServerAccessToken();
  const [dashboard, paperFund] = await Promise.allSettled([
    getOperatingCoreDashboard({ accessToken }),
    getPaperFund({ accessToken }),
  ]);
  return (
    <div className="mx-auto max-w-[1560px] space-y-8">
      <PaperFundPanel initialOverview={paperFund.status === "fulfilled" ? paperFund.value : null} />
      <PortfolioDashboard dashboard={dashboard.status === "fulfilled" ? dashboard.value : null} />
    </div>
  );
}
