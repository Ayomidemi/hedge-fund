import { TickerAnalyst } from "@/components/ticker/TickerAnalyst";
import { getRecentTickerMemos, type TickerMemoSummary } from "@/lib/api";

export default async function TickerAnalystPage() {
  let recentMemos: TickerMemoSummary[] = [];
  let isUnavailable = false;

  try {
    recentMemos = await getRecentTickerMemos();
  } catch {
    isUnavailable = true;
  }

  return <TickerAnalyst recentMemos={recentMemos} isUnavailable={isUnavailable} />;
}
