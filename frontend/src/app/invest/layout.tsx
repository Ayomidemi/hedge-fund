import { InvestShell } from "@/components/shell/InvestShell";
import { getServerUserProfile } from "@/lib/supabase/server";

export default async function InvestLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const user = await getServerUserProfile();
  return (
    <InvestShell canSwitchProducts={user.canSwitchProducts}>{children}</InvestShell>
  );
}
