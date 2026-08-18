import { TickerAnalyst } from "@/components/ticker/TickerAnalyst";
import {
  getRecentTickerMemos,
  getTickerDesk,
  type TickerDesk,
  type TickerMemoSummary,
} from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

type TickerAnalystPageProps = {
  searchParams?: Promise<{ ticker?: string }>;
};

export default async function TickerAnalystPage({ searchParams }: TickerAnalystPageProps) {
  let recentMemos: TickerMemoSummary[] = [];
  let desk: TickerDesk | null = null;
  let isUnavailable = false;
  const accessToken = await getServerAccessToken();
  const ticker = ((await searchParams)?.ticker ?? "").trim().toUpperCase();

  try {
    recentMemos = await getRecentTickerMemos({ accessToken });
  } catch {
    isUnavailable = true;
  }

  if (ticker) {
    try {
      desk = await getTickerDesk(ticker, { accessToken });
    } catch {
      desk = null;
    }
  }

  return (
    <TickerAnalyst
      key={ticker || "index"}
      recentMemos={recentMemos}
      initialTicker={ticker || null}
      initialDesk={desk}
      isUnavailable={isUnavailable}
    />
  );
}
