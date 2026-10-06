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
  const [deskResult, memosResult] = await Promise.allSettled([
    initialTicker && accessToken && startInWorkflow
      ? getTickerDesk(initialTicker, { accessToken }) : Promise.resolve(null),
    getRecentTickerMemos({ accessToken }),
  ]);
  const desk: TickerDesk | null = deskResult.status === "fulfilled" ? deskResult.value : null;
  recentMemos = memosResult.status === "fulfilled" ? memosResult.value : [];
  isUnavailable = memosResult.status === "rejected";

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
