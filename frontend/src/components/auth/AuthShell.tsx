import Link from "next/link";
import type { ReactNode } from "react";
import { theme } from "@/components/ui/theme";

type AuthShellProps = {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer?: ReactNode;
};

export function AuthShell({ title, subtitle, children, footer }: AuthShellProps) {
  return (
    <div className={`flex items-center justify-center px-4 ${theme.page}`}>
      <section className={`w-full max-w-md p-8 shadow-sm ${theme.card}`}>
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-ink text-sm font-semibold text-paper">
            PC
          </div>
          <div>
            <p className="text-sm font-semibold">Pease Capital</p>
            <p className="text-xs text-zinc-500">{subtitle}</p>
          </div>
        </div>

        <h1 className="mt-6 text-xl font-semibold">{title}</h1>

        <div className="mt-6">{children}</div>

        {footer ? <div className="mt-5 border-t border-rule pt-4 dark:border-rule">{footer}</div> : null}
      </section>
    </div>
  );
}

export function authBackLink(href: string, label: string) {
  return (
    <Link href={href} className="text-sm text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200">
      {label}
    </Link>
  );
}
