import { NewsCentre } from "@/components/news/NewsCentre";
import { getNewsOverview, type NewsOverview } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

type NewsPageProps = {
  searchParams?: Promise<{
    ticker?: string;
    market?: string;
    jurisdiction?: string;
    page?: string;
  }>;
};

export default async function NewsPage({ searchParams }: NewsPageProps) {
  let overview: NewsOverview | null = null;
  let unavailable = false;
  const accessToken = await getServerAccessToken();
  const params = (await searchParams) ?? {};
  const ticker = params.ticker?.trim() || undefined;
  const market = params.market === "NG" ? "NG" : params.market === "US" ? "US" : undefined;
  const jurisdiction =
    params.jurisdiction === "NG" || params.jurisdiction === "all"
      ? params.jurisdiction
      : "US";
  const requestedPage = Number.parseInt(params.page ?? "1", 10);
  const page = Number.isFinite(requestedPage) && requestedPage > 0 ? requestedPage : 1;

  try {
    overview = await getNewsOverview(
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

  const overviewKey = ["news-centre", jurisdiction].join(":");

  return (
    <NewsCentre
      key={overviewKey}
      initialOverview={overview}
      initialJurisdiction={jurisdiction}
      unavailable={unavailable}
    />
  );
}
