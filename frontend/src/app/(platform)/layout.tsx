import { AppShell } from "@/components/shell/AppShell";
import { getHealth } from "@/lib/api";
import { getServerAccessToken, getServerUserEmail } from "@/lib/supabase/server";

export default async function PlatformLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  let apiStatus: "connected" | "offline" = "offline";
  const accessToken = await getServerAccessToken();
  const userEmail = await getServerUserEmail();

  try {
    const health = await getHealth({ accessToken });
    if (health.status === "ok") {
      apiStatus = "connected";
    }
  } catch {
    apiStatus = "offline";
  }

  return (
    <AppShell apiStatus={apiStatus} userEmail={userEmail}>
      {children}
    </AppShell>
  );
}
