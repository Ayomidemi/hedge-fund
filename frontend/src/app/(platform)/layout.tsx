import { AppShell } from "@/components/shell/AppShell";
import { getHealth } from "@/lib/api";
import { getServerAccessToken, getServerUserProfile } from "@/lib/supabase/server";

export default async function PlatformLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  let apiStatus: "connected" | "offline" = "offline";
  const accessToken = await getServerAccessToken();
  const user = await getServerUserProfile();

  try {
    const health = await getHealth({ accessToken });
    if (health.status === "ok") {
      apiStatus = "connected";
    }
  } catch {
    apiStatus = "offline";
  }

  return (
    <AppShell
      apiStatus={apiStatus}
      userEmail={user.email}
      userOrgName={user.orgName}
    >
      {children}
    </AppShell>
  );
}
