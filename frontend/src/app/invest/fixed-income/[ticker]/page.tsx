import { InvestFixedIncomeDetail } from "@/components/invest/InvestFixedIncomeDetail";
import {
  getInvestFixedIncomeProduct,
  type InvestFixedIncomeProduct,
} from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function InvestFixedIncomeDetailPage({
  params,
}: {
  params: Promise<{ ticker: string }>;
}) {
  const { ticker } = await params;
  const accessToken = await getServerAccessToken();
  let product: InvestFixedIncomeProduct | null = null;

  try {
    product = await getInvestFixedIncomeProduct(ticker, { accessToken });
  } catch {
    product = null;
  }

  if (!product) {
    return (
      <div className="w-full rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        Fixed-income product could not be loaded.
      </div>
    );
  }

  return <InvestFixedIncomeDetail product={product} />;
}
