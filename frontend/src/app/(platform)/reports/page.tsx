import { ReportsCenter } from "@/components/reports/ReportsCenter";
import {
  getReportOverview,
  getReportSnapshots,
  type MonthlyReport,
  type ReportCenterView,
  type ReportSnapshot,
} from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

type ReportsPageProps = {
  searchParams?: Promise<{ view?: string }>;
};

export default async function ReportsPage({ searchParams }: ReportsPageProps) {
  let report: MonthlyReport | null = null;
  let snapshots: ReportSnapshot[] = [];
  let unavailable = false;
  const accessToken = await getServerAccessToken();
  const params = (await searchParams) ?? {};
  const initialView = isReportCenterView(params.view) ? params.view : "overview";

  try {
    report = await getReportOverview({ kind: "monthly" }, { accessToken });
  } catch {
    unavailable = true;
  }

  try {
    snapshots = await getReportSnapshots(12, { accessToken });
  } catch {
    snapshots = [];
  }

  return (
    <ReportsCenter
      initialReport={report}
      initialSnapshots={snapshots}
      initialView={initialView}
      isUnavailable={unavailable}
    />
  );
}

function isReportCenterView(value: string | undefined): value is ReportCenterView {
  return (
    value === "overview" ||
    value === "attribution" ||
    value === "research" ||
    value === "archive"
  );
}
