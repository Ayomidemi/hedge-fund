import { WatchlistDesk } from "@/components/radar/WatchlistDesk";
import { getRadarWatchlist, type RadarWatchlistItem } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function WatchlistPage() {
  let items: RadarWatchlistItem[] = [];
  let unavailable = false;
  const accessToken = await getServerAccessToken();

  try {
    const payload = await getRadarWatchlist({ accessToken });
    items = payload.items;
  } catch {
    unavailable = true;
  }

  return <WatchlistDesk initialItems={items} unavailable={unavailable} />;
}
