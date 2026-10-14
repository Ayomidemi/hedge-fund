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
      <div className="rounded-sm border border-rule bg-paper p-6 text-sm text-zinc-500 dark:border-rule dark:bg-paper">
        {ticker.toUpperCase()} could not be loaded.
      </div>
    );
  }

  return (
    <InvestInstrumentDetail
      key={instrument.ticker}
      instrument={instrument}
      initialTab={query.order === "1" ? "order" : "overview"}
    />
  );
}
