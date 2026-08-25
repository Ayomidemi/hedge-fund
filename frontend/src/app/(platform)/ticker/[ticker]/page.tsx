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
    try {
      desk = await getTickerDesk(ticker, { accessToken });
    } catch {
      desk = null;
    }
    try {
      chart = await getTickerChart(ticker, "1d", { accessToken });
    } catch {
      chart = null;
    }
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
