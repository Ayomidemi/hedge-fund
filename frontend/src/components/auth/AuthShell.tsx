import Link from "next/link";
import type { ReactNode } from "react";

type AuthShellProps = {
  title: string;
  subtitle: string;
  children: ReactNode;
  footer?: ReactNode;
};

export function AuthShell({ title, subtitle, children, footer }: AuthShellProps) {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#f6f7f4] px-4 dark:bg-zinc-950">
      <section className="w-full max-w-md rounded-2xl border border-zinc-200 bg-white p-8 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-zinc-950 text-sm font-semibold text-white dark:bg-zinc-100 dark:text-zinc-950">
            PC
          </div>
          <div>
            <p className="text-sm font-semibold">Pease Capital</p>
            <p className="text-xs text-zinc-500">{subtitle}</p>
          </div>
        </div>

        <h1 className="mt-6 text-xl font-semibold">{title}</h1>

        <div className="mt-6">{children}</div>

        {footer ? <div className="mt-5 border-t border-zinc-200 pt-4 dark:border-zinc-800">{footer}</div> : null}
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
