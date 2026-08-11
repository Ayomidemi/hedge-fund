"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { AuthShell } from "@/components/auth/AuthShell";
import { FormField } from "@/components/ui/FormField";
import { buttonPrimaryClassName } from "@/components/ui/form-styles";
import { toast } from "@/components/ui/ToastProvider";
import { createClient, isSupabaseConfigured } from "@/lib/supabase/client";

type AuthMode = "sign-in" | "sign-up";

export function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const nextPath = searchParams.get("next") || "/";
  const [mode, setMode] = useState<AuthMode>("sign-in");
  const [fullName, setFullName] = useState("");
  const [orgName, setOrgName] = useState("");
  const [startingCapital, setStartingCapital] = useState("1000");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [pending, setPending] = useState(false);

  useEffect(() => {
    const error = searchParams.get("error");
    if (error) {
      toast.error(error);
    }
  }, [searchParams]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPending(true);

    try {
      const supabase = createClient();

      if (mode === "sign-in") {
        const { error } = await supabase.auth.signInWithPassword({
          email: email.trim(),
          password,
        });
        if (error) {
          throw error;
        }
        router.replace(nextPath);
        router.refresh();
        return;
      }

      const capital = Number(startingCapital);
      if (!Number.isFinite(capital) || capital < 1000) {
        toast.error("Starting capital must be at least 1,000.");
        return;
      }

      const { error } = await supabase.auth.signUp({
        email: email.trim(),
        password,
        options: {
          data: {
            full_name: fullName.trim(),
            org_name: orgName.trim(),
            starting_capital: capital.toFixed(2),
          },
        },
      });
      if (error) {
        throw error;
      }
      toast.success(
        "Account created. Check your email if confirmation is required, then sign in.",
      );
      setMode("sign-in");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Authentication failed.",
      );
    } finally {
      setPending(false);
    }
  }

  if (!isSupabaseConfigured()) {
    return (
      <AuthShell title="Auth not configured" subtitle="Setup required">
        <p className="text-sm leading-6 text-zinc-600 dark:text-zinc-300">
          Add <code className="text-xs">NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
          <code className="text-xs">NEXT_PUBLIC_SUPABASE_ANON_KEY</code> to{" "}
          <code className="text-xs">frontend/.env</code>.
        </p>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title={mode === "sign-in" ? "Sign in" : "Create account"}
      subtitle="Fund operating system"
    >
      <div className="grid grid-cols-2 gap-2 rounded-xl bg-zinc-100 p-1 dark:bg-zinc-900">
        <button
          type="button"
          className={`rounded-lg px-3 py-2 text-sm font-medium ${
            mode === "sign-in"
              ? "bg-white text-zinc-950 shadow-sm dark:bg-zinc-800 dark:text-zinc-50"
              : "text-zinc-600 dark:text-zinc-400"
          }`}
          onClick={() => setMode("sign-in")}
        >
          Sign in
        </button>
        <button
          type="button"
          className={`rounded-lg px-3 py-2 text-sm font-medium ${
            mode === "sign-up"
              ? "bg-white text-zinc-950 shadow-sm dark:bg-zinc-800 dark:text-zinc-50"
              : "text-zinc-600 dark:text-zinc-400"
          }`}
          onClick={() => setMode("sign-up")}
        >
          Create account
        </button>
      </div>

      <form className="mt-6 space-y-4" onSubmit={handleSubmit}>
        {mode === "sign-up" ? (
          <>
            <FormField
              label="Your name"
              autoComplete="name"
              required
              value={fullName}
              onChange={setFullName}
            />

            <FormField
              label="Organization"
              autoComplete="organization"
              required
              value={orgName}
              onChange={setOrgName}
            />

            <FormField
              label="Starting capital"
              type="number"
              required
              min={1000}
              step={100}
              inputMode="decimal"
              helper="Minimum 1,000."
              value={startingCapital}
              onChange={setStartingCapital}
            />
          </>
        ) : null}

        <FormField
          label="Email"
          type="email"
          autoComplete="email"
          required
          value={email}
          onChange={setEmail}
        />

        <FormField
          label="Password"
          type="password"
          autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
          required
          minLength={8}
          helper={mode === "sign-up" ? "Use at least 8 characters." : undefined}
          labelAction={
            mode === "sign-in" ? (
              <a
                href="/login/forgot-password"
                className="text-xs text-zinc-500 hover:text-zinc-800 dark:hover:text-zinc-200"
              >
                Forgot password?
              </a>
            ) : undefined
          }
          value={password}
          onChange={setPassword}
        />

        <button
          type="submit"
          disabled={pending}
          className={`${buttonPrimaryClassName} w-full`}
        >
          {pending
            ? "Working..."
            : mode === "sign-in"
              ? "Sign in"
              : "Create account"}
        </button>
      </form>
    </AuthShell>
  );
}
