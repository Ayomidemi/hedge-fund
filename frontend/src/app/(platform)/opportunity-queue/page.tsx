import { OpportunityQueue } from "@/components/opportunities/OpportunityQueue";
import {
  getOpportunityQueue,
  type OpportunityQueue as OpportunityQueueData,
} from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function OpportunityQueuePage() {
  let queue: OpportunityQueueData | null = null;
  let unavailable = false;
  const accessToken = await getServerAccessToken();

  try {
    queue = await getOpportunityQueue({ accessToken });
  } catch {
    unavailable = true;
  }

  return <OpportunityQueue queue={queue} isUnavailable={unavailable} />;
}
