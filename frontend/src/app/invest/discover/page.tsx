import Link from "next/link";
import { getInvestDiscover } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function InvestDiscoverPage() {
  const accessToken = await getServerAccessToken();
  let discover = {
    summary: "Retail Discover will reuse Market Radar with simpler language.",
    sections: ["Trending", "Big Movers", "Unusual Activity"],
  };
  try {
    discover = await getInvestDiscover({ accessToken });
  } catch {
    // keep fallback
  }

  return (
    <div className="mx-auto max-w-3xl rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
      <p className="text-sm text-zinc-600 dark:text-zinc-400">{discover.summary}</p>
      <ul className="mt-4 space-y-2 text-sm">
        {discover.sections.map((section) => (
          <li key={section} className="rounded-xl bg-zinc-50 px-4 py-3 dark:bg-zinc-900">
            {section}
          </li>
        ))}
      </ul>
      <Link href="/invest/search" className="mt-5 inline-block text-sm font-medium underline">
        Search a name instead
      </Link>
    </div>
  );
}
