import { Suspense } from "react";

import { LoginForm } from "@/components/auth/LoginForm";

export default function LoginPage() {
  return (
    <Suspense
      fallback={
        <div className="flex min-h-screen items-center justify-center bg-paper dark:bg-paper">
          <p className="text-sm text-zinc-500">Loading sign in...</p>
        </div>
      }
    >
      <LoginForm />
    </Suspense>
  );
}
