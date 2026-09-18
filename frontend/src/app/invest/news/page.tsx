import { InvestNews } from "@/components/invest/InvestNews";
import { getInvestNews, type InvestNewsOverview } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

type NewsPageProps = {
  searchParams?: Promise<{
    ticker?: string;
    market?: string;
    jurisdiction?: string;
    page?: string;
  }>;
};

export default async function InvestNewsPage({ searchParams }: NewsPageProps) {
  let overview: InvestNewsOverview | null = null;
  let unavailable = false;
  const accessToken = await getServerAccessToken();
  const params = (await searchParams) ?? {};
  const ticker = params.ticker?.trim() || undefined;
  const market = params.market === "NG" ? "NG" : params.market === "US" ? "US" : undefined;
  const jurisdiction =
    params.jurisdiction === "NG" || params.jurisdiction === "US"
      ? params.jurisdiction
      : "all";
  const requestedPage = Number.parseInt(params.page ?? "1", 10);
  const page = Number.isFinite(requestedPage) && requestedPage > 0 ? requestedPage : 1;

  try {
    overview = await getInvestNews(
      {
        ticker,
        market,
        jurisdiction,
        page,
        page_size: 20,
        ticker_page: 1,
        ticker_page_size: 8,
      },
      { accessToken },
    );
  } catch {
    unavailable = true;
  }

  const overviewKey = ["invest-news", jurisdiction, ticker ?? ""].join(":");

  return (
    <InvestNews
      key={overviewKey}
      initialOverview={overview}
      initialJurisdiction={jurisdiction}
      unavailable={unavailable}
    />
  );
}
