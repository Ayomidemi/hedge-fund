import { PaperFundPanel } from "@/components/portfolio/PaperFundPanel";
import { getPaperFund } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function Home() {
  const accessToken = await getServerAccessToken();
  const capital = await getPaperFund({ accessToken }).catch(() => null);
  return (
    <div className="mx-auto max-w-[1560px] space-y-8">
      <PaperFundPanel initialOverview={capital} />
    </div>
  );
}
