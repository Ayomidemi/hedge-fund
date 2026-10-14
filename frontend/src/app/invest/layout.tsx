import { LiveDataProvider } from "@/components/providers/LiveDataProvider";
import { InvestShell } from "@/components/shell/InvestShell";
import { getServerUserProfile } from "@/lib/supabase/server";

export default async function InvestLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const user = await getServerUserProfile();

  return (
    <LiveDataProvider>
      <InvestShell userOrgName={user.orgName} canSwitchProducts={user.canSwitchProducts}>
        {children}
      </InvestShell>
    </LiveDataProvider>
  );
}
