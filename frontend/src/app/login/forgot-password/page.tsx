import { Suspense } from "react";

import { ForgotPasswordForm } from "@/components/auth/ForgotPasswordForm";

export default function ForgotPasswordPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-paper dark:bg-paper">
          <p className="text-sm text-zinc-500">Loading...</p>
        </div>
      }
    >
      <ForgotPasswordForm />
    </Suspense>
  );
}
