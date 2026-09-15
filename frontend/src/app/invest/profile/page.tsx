import Link from "next/link";
import { buttonSecondaryClassName } from "@/components/ui/form-styles";

export default function InvestProfilePage() {
  return (
    <div className="mx-auto max-w-3xl rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
      <h2 className="text-lg font-semibold">Pease Invest</h2>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400">
        You decide the trades. This paper account is separate from Pease Capital fund
        books.
      </p>
      <Link href="/settings" className={`${buttonSecondaryClassName} mt-5`}>
        Account settings
      </Link>
    </div>
  );
}
