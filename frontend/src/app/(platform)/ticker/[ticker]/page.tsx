import { TickerHub } from "@/components/ticker/TickerHub";
import {
  getTickerChart,
  getTickerDesk,
  type RadarWatchlistChart,
  type TickerDesk,
} from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

type TickerPageProps = {
  params: Promise<{ ticker: string }>;
};

export default async function TickerPage({ params }: TickerPageProps) {
  const { ticker: rawTicker } = await params;
  const ticker = decodeURIComponent(rawTicker).trim().toUpperCase();
  const accessToken = await getServerAccessToken();
  let desk: TickerDesk | null = null;
  let chart: RadarWatchlistChart | null = null;

  if (accessToken) {
    const [deskResult, chartResult] = await Promise.allSettled([
      getTickerDesk(ticker, { accessToken }), getTickerChart(ticker, "1d", { accessToken }),
    ]);
    desk = deskResult.status === "fulfilled" ? deskResult.value : null;
    chart = chartResult.status === "fulfilled" ? chartResult.value : null;
  }

  return (
    <TickerHub
      key={ticker}
      ticker={ticker}
      initialDesk={desk}
      initialChart={chart}
      unavailable={!accessToken}
    />
  );
}
