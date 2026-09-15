import { InvestShell } from "@/components/shell/InvestShell";

export default function InvestLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return <InvestShell>{children}</InvestShell>;
}
