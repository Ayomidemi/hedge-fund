import { InvestInstrumentDetail } from "@/components/invest/InvestInstrumentDetail";
import {
  getInvestInstrument,
  getInvestInstrumentResearch,
  type InvestInstrument,
  type InvestInstrumentResearch,
} from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function InvestInstrumentPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  let instrument: InvestInstrument | null = null;
  let research: InvestInstrumentResearch | null = null;
  const accessToken = await getServerAccessToken();
  try {
    [instrument, research] = await Promise.all([
      getInvestInstrument(ticker, { accessToken }),
      getInvestInstrumentResearch(ticker, { accessToken }),
    ]);
  } catch {
    instrument = null;
    research = null;
  }

  if (!instrument) {
    return (
      <div className="rounded-2xl border border-zinc-200 bg-white p-6 text-sm text-zinc-500 dark:border-zinc-800 dark:bg-zinc-950">
        {ticker.toUpperCase()} could not be loaded.
      </div>
    );
  }

  return <InvestInstrumentDetail instrument={instrument} research={research} />;
}
