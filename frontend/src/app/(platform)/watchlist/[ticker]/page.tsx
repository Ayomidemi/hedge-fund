import { redirect } from "next/navigation";
import { tickerHubPath } from "@/lib/ticker-hub-path";

type WatchlistTickerRedirectProps = {
  params: Promise<{ ticker: string }>;
};

export default async function WatchlistTickerRedirectPage({
  params,
}: WatchlistTickerRedirectProps) {
  const { ticker } = await params;
  redirect(tickerHubPath(decodeURIComponent(ticker)));
}
