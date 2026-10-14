"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LiveStatusIndicator } from "@/components/shell/LiveStatusIndicator";
import { ProductSwitcher } from "@/components/shell/ProductSwitcher";
import { CapitalIcon, type CapitalIconName } from "@/components/ui/CapitalIcon";
import { theme } from "@/components/ui/theme";

export type WorkspaceNavItem = {
  label: string;
  href: string;
  icon: CapitalIconName;
};

export type WorkspaceNavGroup = {
  label: string;
  items: WorkspaceNavItem[];
};

type WorkspaceShellProps = {
  product: "capital" | "invest";
  homeHref: string;
  navigationGroups: WorkspaceNavGroup[];
  accountHref: string;
  accountHint: string;
  userOrgName: string | null;
  canSwitchProducts?: boolean;
  isItemActive: (pathname: string, href: string) => boolean;
  titleForPath: (pathname: string, activeLabel: string | undefined) => string;
  children: React.ReactNode;
};

export function WorkspaceShell({
  product,
  homeHref,
  navigationGroups,
  accountHref,
  accountHint,
  userOrgName,
  canSwitchProducts = false,
  isItemActive,
  titleForPath,
  children,
}: WorkspaceShellProps) {
  const pathname = usePathname();
  const productLabel = product === "capital" ? "Capital" : "Invest";
  const active = navigationGroups
    .flatMap((group) => group.items)
    .find((item) => isItemActive(pathname, item.href));
  const title = titleForPath(pathname, active?.label);
  const initials = (userOrgName ?? "PC").slice(0, 2).toUpperCase();

  const renderNavigation = () =>
    navigationGroups.map((group) => (
      <div key={group.label} className="mb-6 last:mb-0">
        <p className={`mb-2 px-3 text-[11px] font-semibold uppercase tracking-[0.14em] ${theme.muted}`}>
          {group.label}
        </p>
        <div className="space-y-0.5">
          {group.items.map((item) => {
            const current = isItemActive(pathname, item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                aria-current={current ? "page" : undefined}
                className={`flex items-center gap-3 rounded-lg px-3 py-2 text-[13px] ${
                  current ? theme.navActive : theme.navIdle
                }`}
              >
                <CapitalIcon name={item.icon} className="h-[17px] w-[17px] shrink-0" />
                {item.label}
              </Link>
            );
          })}
        </div>
      </div>
    ));

  return (
    <div className={`pease-workspace flex ${theme.page}`}>
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-r border-rule bg-paper lg:flex">
        <Link href={homeHref} className="flex items-center gap-3 px-6 py-7">
          <span className="pease-editorial text-[23px]">
            Pease <span className={theme.muted}>{productLabel}</span>
          </span>
        </Link>
        {canSwitchProducts ? (
          <div className="px-5 pb-5">
            <ProductSwitcher active={product} />
          </div>
        ) : null}
        <nav aria-label={`${productLabel} navigation`} className="flex-1 overflow-y-auto px-3 py-2">
          {renderNavigation()}
        </nav>
        <Link
          href={accountHref}
          className="m-3 flex items-center gap-3 rounded-lg border border-rule px-3 py-3 text-sm hover:bg-hover"
        >
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-action text-xs font-semibold text-action-ink">
            {initials}
          </span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-xs font-medium">{userOrgName ?? "Your account"}</span>
            <span className={`text-[11px] ${theme.muted}`}>{accountHint}</span>
          </span>
          <CapitalIcon name="settings" className={`h-4 w-4 ${theme.muted}`} />
        </Link>
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex min-h-16 flex-wrap items-center justify-between gap-3 border-b border-rule bg-paper px-5 py-4 sm:px-8">
          <div className="flex items-center gap-3 text-sm">
            <span className={theme.muted}>{productLabel}</span>
            <span className="text-zinc-300 dark:text-zinc-600">/</span>
            <h1 className="font-medium">{title}</h1>
          </div>
          <LiveStatusIndicator />
        </header>
        <details className="border-b border-rule bg-paper px-5 py-3 lg:hidden">
          <summary className="cursor-pointer text-xs font-medium">Menu</summary>
          <nav aria-label={`${productLabel} mobile navigation`} className="mt-5 grid grid-cols-2 gap-3">
            {renderNavigation()}
          </nav>
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <ProductSwitcher active={product} visible={canSwitchProducts} />
            <Link href={accountHref} className={`text-sm ${theme.muted}`}>
              {accountHint} →
            </Link>
          </div>
        </details>
        <main className="flex-1 px-4 py-6 sm:px-8 sm:py-8 xl:px-10">{children}</main>
      </div>
    </div>
  );
}
