import { NewsCentre } from "@/components/news/NewsCentre";
import { getNewsOverview, type NewsOverview } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

type NewsPageProps = {
  searchParams?: Promise<{ ticker?: string; market?: string; jurisdiction?: string }>;
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

  try {
    overview = await getNewsOverview(
      {
        ticker,
        market,
        jurisdiction,
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
