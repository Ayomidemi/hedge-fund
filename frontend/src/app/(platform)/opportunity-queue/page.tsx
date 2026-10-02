import { OpportunityQueue } from "@/components/opportunities/OpportunityQueue";
import { getPaperFund } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function OpportunityQueuePage() {
  const accessToken = await getServerAccessToken();
  const overview = await getPaperFund({ accessToken }).catch(() => null);
  return <OpportunityQueue overview={overview} />;
}
