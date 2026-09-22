import { InvestProfileTabs } from "@/components/invest/InvestProfileTabs";
import { getInvestProfile, type InvestProfile } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function InvestProfilePage() {
  const accessToken = await getServerAccessToken();
  let profile: InvestProfile | null = null;

  try {
    profile = await getInvestProfile({ accessToken });
  } catch {
    profile = null;
  }

  if (!profile) {
    return (
      <div className="w-full rounded-2xl border border-red-200 bg-red-50 p-5 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-200">
        Invest profile could not load.
      </div>
    );
  }

  return <InvestProfileTabs profile={profile} />;
}
