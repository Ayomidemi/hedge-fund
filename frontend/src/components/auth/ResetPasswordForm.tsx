"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AuthShell, authBackLink } from "@/components/auth/AuthShell";
import { FormField } from "@/components/ui/FormField";
import { buttonPrimaryClassName } from "@/components/ui/form-styles";
import { toast } from "@/components/ui/ToastProvider";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";

export function ResetPasswordForm() {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pending, setPending] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!isSupabaseConfigured()) {
      return;
    }

    const supabase = createClient();
    supabase.auth.getSession().then(({ data }) => {
      setReady(Boolean(data.session));
    });
  }, []);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (password.length < 8) {
      toast.error("Password must be at least 8 characters.");
      return;
    }

    if (password !== confirmPassword) {
      toast.error("Passwords do not match.");
      return;
    }

    setPending(true);

    try {
      const supabase = createClient();
      const { error } = await supabase.auth.updateUser({ password });

      if (error) {
        throw error;
      }

      toast.success("Password updated.");
      router.replace("/");
      router.refresh();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Could not update password.",
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

  if (!ready) {
    return (
      <AuthShell
        title="Reset link expired"
        subtitle="Request a new one"
        footer={authBackLink("/login/forgot-password", "← Request new link")}
      >
        <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-300">
          Open the reset link from your email, or request a fresh one.
        </p>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Set new password"
      subtitle="Choose a new password for your account"
      footer={authBackLink("/login", "← Back to sign in")}
    >
      <form className="space-y-4" onSubmit={handleSubmit}>
        <FormField
          label="New password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          helper="Use at least 8 characters."
          value={password}
          onChange={setPassword}
        />

        <FormField
          label="Confirm password"
          type="password"
          autoComplete="new-password"
          required
          minLength={8}
          helper="Re-enter the same password."
          value={confirmPassword}
          onChange={setConfirmPassword}
        />

        <button
          type="submit"
          disabled={pending}
          className={`${buttonPrimaryClassName} w-full`}
        >
          {pending ? "Updating..." : "Update password"}
        </button>
      </form>
    </AuthShell>
  );
}
