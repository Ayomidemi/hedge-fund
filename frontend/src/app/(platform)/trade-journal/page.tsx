import { TradeJournal } from "@/components/trades/TradeJournal";
import { getTradeJournal, type TradeJournal as TradeJournalData } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function TradeJournalPage() {
  let journal: TradeJournalData | null = null;
  let unavailable = false;
  const accessToken = await getServerAccessToken();

  try {
    journal = await getTradeJournal({ accessToken });
  } catch {
    unavailable = true;
  }

  return <TradeJournal journal={journal} isUnavailable={unavailable} />;
}
