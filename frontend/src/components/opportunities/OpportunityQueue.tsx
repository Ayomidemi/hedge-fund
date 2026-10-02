import { PaperFundPanel } from "@/components/portfolio/PaperFundPanel";
import type { PaperFundOverview } from "@/lib/api";

export function OpportunityQueue({ overview }: { overview: PaperFundOverview | null }) {
  return (
    <div className="mx-auto max-w-[1400px]">
      <PaperFundPanel initialOverview={overview} mode="queue" />
    </div>
  );
}
