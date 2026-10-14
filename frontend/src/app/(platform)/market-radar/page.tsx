import { Suspense } from "react";
import { MarketRadar } from "@/components/radar/MarketRadar";
import { RadarSkeleton } from "@/components/radar/RadarSkeleton";
import { PaperFundPanel } from "@/components/portfolio/PaperFundPanel";
import { getMarketRadarDesk, getPaperFund } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

type Token = ReturnType<typeof getServerAccessToken>;
async function RadarData({ token }: { token: Token }) {
  const overview = await getMarketRadarDesk({ accessToken: await token }).catch(() => null);
  return <MarketRadar initialOverview={overview} />;
}
async function TradingData({ token }: { token: Token }) {
  const overview = await getPaperFund({ accessToken: await token }).catch(() => null);
  return <PaperFundPanel initialOverview={overview} mode="radar" />;
}
export default function MarketRadarPage() {
  const token = getServerAccessToken();
  return <div className="mx-auto max-w-[1440px] space-y-5">
    <header><h2 className="pease-editorial text-3xl sm:text-4xl">The market, at a glance.</h2>
      <p className="mt-2 text-sm text-zinc-500">Find unusual activity, follow your names, and see where the data is still incomplete.</p></header>
    <Suspense fallback={<div role="status" className="min-h-20 border-y border-zinc-200 py-6 text-sm text-zinc-500 dark:border-zinc-800">Loading trading controls…</div>}>
      <TradingData token={token} />
    </Suspense>
    <Suspense fallback={<RadarSkeleton />}><RadarData token={token} /></Suspense>
  </div>;
}
