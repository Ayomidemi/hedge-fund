import { InvestInstrumentDetail } from "@/components/invest/InvestInstrumentDetail";
import { getInvestInstrument, type InvestInstrument } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function InvestInstrumentPage({
  params,
  searchParams,
}: {
  params: Promise<{ ticker: string }>;
  searchParams: Promise<{ order?: string }>;
}) {
  const { ticker } = await params;
  const query = await searchParams;
  let instrument: InvestInstrument | null = null;
  const accessToken = await getServerAccessToken();
  try {
    instrument = await getInvestInstrument(ticker, { accessToken });
  } catch {
    instrument = null;
  }

  if (!instrument) {
    return (
      <div className="rounded-2xl border border-zinc-200 bg-white p-6 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950">
        {ticker.toUpperCase()} could not be loaded.
      </div>
    );
  }

  return (
    <InvestInstrumentDetail
      instrument={instrument}
      initialTab={query.order === "1" ? "order" : "overview"}
    />
  );
}
