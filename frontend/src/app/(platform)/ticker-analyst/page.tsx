import { TickerAnalyst } from "@/components/ticker/TickerAnalyst";
import { getRecentTickerMemos, type TickerMemoSummary } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function TickerAnalystPage() {
  let recentMemos: TickerMemoSummary[] = [];
  let isUnavailable = false;
  const accessToken = await getServerAccessToken();

  try {
    recentMemos = await getRecentTickerMemos({ accessToken });
  } catch {
    isUnavailable = true;
  }

  return <TickerAnalyst recentMemos={recentMemos} isUnavailable={isUnavailable} />;
}
