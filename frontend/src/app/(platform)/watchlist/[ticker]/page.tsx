import { WatchlistTicker } from "@/components/radar/WatchlistTicker";
import {
  getRadarWatchlistChart,
  getRadarWatchlistTicker,
  type RadarWatchlistChart,
  type RadarWatchlistDetail,
} from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

type WatchlistTickerPageProps = {
  params: Promise<{ ticker: string }>;
};

export default async function WatchlistTickerPage({ params }: WatchlistTickerPageProps) {
  const { ticker } = await params;
  const decoded = decodeURIComponent(ticker);
  let detail: RadarWatchlistDetail | null = null;
  let chart: RadarWatchlistChart | null = null;
  const accessToken = await getServerAccessToken();
  const unavailable = !accessToken;

  if (accessToken) {
    try {
      detail = await getRadarWatchlistTicker(decoded, { accessToken });
    } catch {
      detail = null;
    }
    try {
      chart = await getRadarWatchlistChart(decoded, "1d", { accessToken });
    } catch {
      chart = null;
    }
  }

  return (
    <WatchlistTicker
      ticker={decoded.toUpperCase()}
      initialDetail={detail}
      initialChart={chart}
      unavailable={unavailable}
    />
  );
}
