import { InvestHome } from "@/components/invest/InvestHome";
import { getInvestHome, type InvestHome as InvestHomeData } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function InvestHomePage() {
  let home: InvestHomeData | null = null;
  const accessToken = await getServerAccessToken();
  try {
    home = await getInvestHome({ accessToken });
  } catch {
    home = null;
  }
  return <InvestHome home={home} />;
}
