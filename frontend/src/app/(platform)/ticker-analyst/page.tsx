import { redirect } from "next/navigation";
import { TickerAnalyst } from "@/components/ticker/TickerAnalyst";
import {
  getRecentTickerMemos,
  getTickerDesk,
  type TickerDesk,
  type TickerMemoSummary,
} from "@/lib/api";
import { tickerHubPath } from "@/lib/ticker-hub-path";
import { getServerAccessToken } from "@/lib/supabase/server";

type TickerAnalystPageProps = {
  searchParams?: Promise<{ ticker?: string; analyze?: string; memo?: string; workflow?: string }>;
};

export default async function TickerAnalystPage({ searchParams }: TickerAnalystPageProps) {
  let recentMemos: TickerMemoSummary[] = [];
  let isUnavailable = false;
  const accessToken = await getServerAccessToken();
  const params = await searchParams;
  const ticker = (params?.ticker ?? "").trim().toUpperCase();
  const analyzeTicker = (params?.analyze ?? "").trim().toUpperCase();
  const startInWorkflow = params?.workflow === "1";

  if (ticker && !params?.analyze && !params?.memo) {
    redirect(tickerHubPath(ticker));
  }

  if (analyzeTicker && !startInWorkflow) {
    redirect(tickerHubPath(analyzeTicker));
  }

  const initialTicker = analyzeTicker || ticker || null;
  let desk: TickerDesk | null = null;
  if (initialTicker && accessToken && startInWorkflow) {
    try {
      desk = await getTickerDesk(initialTicker, { accessToken });
    } catch {
      desk = null;
    }
  }

  try {
    recentMemos = await getRecentTickerMemos({ accessToken });
  } catch {
    isUnavailable = true;
  }

  return (
    <TickerAnalyst
      key={initialTicker || "index"}
      recentMemos={recentMemos}
      initialTicker={initialTicker}
      initialDesk={desk}
      startInWorkflow={startInWorkflow}
      isUnavailable={isUnavailable}
    />
  );
}
