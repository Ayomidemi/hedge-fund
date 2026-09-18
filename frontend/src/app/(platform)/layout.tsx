import { LiveDataProvider } from "@/components/providers/LiveDataProvider";
import { AppShell } from "@/components/shell/AppShell";
import { getServerUserProfile } from "@/lib/supabase/server";

export default async function PlatformLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const user = await getServerUserProfile();

  return (
    <LiveDataProvider>
      <AppShell
        userOrgName={user.orgName}
        canSwitchProducts={user.canSwitchProducts}
      >
        {children}
      </AppShell>
    </LiveDataProvider>
  );
}
