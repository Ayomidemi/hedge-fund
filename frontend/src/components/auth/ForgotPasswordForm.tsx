"use client";

import { FormEvent, useState } from "react";
import { AuthShell, authBackLink } from "@/components/auth/AuthShell";
import { FormField } from "@/components/ui/FormField";
import { buttonPrimaryClassName } from "@/components/ui/form-styles";
import { toast } from "@/components/ui/ToastProvider";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";

export function ForgotPasswordForm() {
  const [email, setEmail] = useState("");
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);

    try {
      if (!isSupabaseConfigured()) {
        throw new Error("Supabase is not configured.");
      }

      const supabase = createClient();
      const redirectTo = `${window.location.origin}/auth/callback?next=${encodeURIComponent("/auth/reset-password")}`;
      const { error } = await supabase.auth.resetPasswordForEmail(email.trim(), {
        redirectTo,
      });

      if (error) {
        throw error;
      }

      toast.success("If that email exists, a reset link is on its way.");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Could not send reset email.",
      );
    } finally {
      setPending(false);
    }
  }

  if (!isSupabaseConfigured()) {
    return (
      <AuthShell title="Auth not configured" subtitle="Setup required">
        <p className="text-sm text-zinc-600 dark:text-zinc-300">
          Supabase environment variables are missing.
        </p>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Forgot password"
      subtitle="We will email you a reset link"
      footer={authBackLink("/login", "← Back to sign in")}
    >
      <form className="space-y-4" onSubmit={handleSubmit}>
        <FormField
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={setEmail}
        />

        <button
          type="submit"
          disabled={pending}
          className={`${buttonPrimaryClassName} w-full`}
        >
          {pending ? "Sending..." : "Send reset link"}
        </button>
      </form>
    </AuthShell>
  );
}
