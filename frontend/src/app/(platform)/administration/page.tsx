import { Administration } from "@/components/administration/Administration";
import { getAdministrationOverview, type AdministrationOverview } from "@/lib/api";
import { getServerAccessToken } from "@/lib/supabase/server";

export default async function AdministrationPage() {
  let overview: AdministrationOverview | null = null;
  let isUnavailable = false;
  const accessToken = await getServerAccessToken();

  try {
    overview = await getAdministrationOverview(undefined, { accessToken });
  } catch {
    isUnavailable = true;
  }

  return <Administration initialOverview={overview} isUnavailable={isUnavailable} />;
}
