import { ResearchLab } from "@/components/research/ResearchLab";
import { getResearchLabOverview, type ResearchLabOverview } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function ResearchLabPage() {
  let overview: ResearchLabOverview | null = null;
  let unavailable = false;
  const accessToken = await getServerAccessToken();

  try {
    overview = await getResearchLabOverview({ accessToken });
  } catch {
    unavailable = true;
  }

  return <ResearchLab initialOverview={overview} unavailable={unavailable} />;
}
