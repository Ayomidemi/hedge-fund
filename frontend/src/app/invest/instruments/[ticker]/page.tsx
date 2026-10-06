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
      <div className="rounded-sm border border-stone-300/70 bg-[#fffefb] p-6 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-[#151613]">
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
