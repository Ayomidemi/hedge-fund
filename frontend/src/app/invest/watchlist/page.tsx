import { InvestWatchlist } from "@/components/invest/InvestWatchlist";
import { getInvestWatchlist, type InvestWatchlistItem } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function InvestWatchlistPage() {
  const accessToken = await getServerAccessToken();
  let items: InvestWatchlistItem[] = [];
  let error: string | null = null;
  try {
    items = await getInvestWatchlist({ accessToken });
  } catch (caught) {
    error = caught instanceof Error ? caught.message : "Watchlist could not be loaded.";
  }
  return <InvestWatchlist items={items} error={error} />;
}
