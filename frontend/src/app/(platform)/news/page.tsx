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
      },
      { accessToken },
    );
  } catch {
    unavailable = true;
  }

  return (
    <NewsCentre
      initialOverview={overview}
      initialJurisdiction={jurisdiction}
      unavailable={unavailable}
    />
  );
}
