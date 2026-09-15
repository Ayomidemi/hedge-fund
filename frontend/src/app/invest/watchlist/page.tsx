import { InvestWatchlist } from "@/components/invest/InvestWatchlist";
import { getInvestWatchlist, type InvestWatchlistItem } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function InvestWatchlistPage() {
  const accessToken = await getServerAccessToken();
  let items: InvestWatchlistItem[] = [];
  try {
    items = await getInvestWatchlist({ accessToken });
  } catch {
    items = [];
  }
  return <InvestWatchlist items={items} />;
}
