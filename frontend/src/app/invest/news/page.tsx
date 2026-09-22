import { InvestNews } from "@/components/invest/InvestNews";
import {
  getInvestConfig,
  getInvestNews,
  type InvestConfig,
  type InvestNewsOverview,
} from "@/lib/api";
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
  let config: InvestConfig | null = null;
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
    config = await getInvestConfig({ accessToken });
  } catch {
    config = null;
  }

  try {
    const sectionPageSize = config?.news.section_page_size;
    overview = await getInvestNews(
      {
        ticker,
        market,
        jurisdiction,
        page,
        page_size: config?.news.headlines_page_size,
        ticker_page: 1,
        ticker_page_size: config?.news.ticker_page_size,
        income_page: 1,
        income_page_size: sectionPageSize,
        for_you_page: 1,
        for_you_page_size: sectionPageSize,
        markets_page: 1,
        markets_page_size: sectionPageSize,
        saved_page: 1,
        saved_page_size: sectionPageSize,
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
      settings={config?.news ?? null}
      unavailable={unavailable}
    />
  );
}
