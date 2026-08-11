"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { FormField } from "@/components/ui/FormField";
import {
  buttonPrimaryClassName,
  buttonSecondaryClassName,
} from "@/components/ui/form-styles";
import { toast } from "@/components/ui/ToastProvider";
import { createClient } from "@/lib/supabase/client";

type UserProfile = {
  email: string;
  fullName: string;
  orgName: string;
  startingCapital: string | null;
};

type SettingsTab = "profile" | "password" | "session";

const tabs: { key: SettingsTab; label: string }[] = [
  { key: "profile", label: "Profile" },
  { key: "password", label: "Password" },
  { key: "session", label: "Session" },
];

export function SettingsPage() {
  const router = useRouter();
  const [activeTab, setActiveTab] = useState<SettingsTab>("profile");
  const [loading, setLoading] = useState(true);
  const [profilePending, setProfilePending] = useState(false);
  const [passwordPending, setPasswordPending] = useState(false);
  const [logoutPending, setLogoutPending] = useState(false);
  const [profile, setProfile] = useState<UserProfile>({
    email: "",
    fullName: "",
    orgName: "",
    startingCapital: null,
  });
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  useEffect(() => {
    const supabase = createClient();

    supabase.auth.getUser().then(({ data, error }) => {
      if (error || !data.user) {
        toast.error("Could not load your profile.");
        setLoading(false);
        return;
      }

      const metadata = data.user.user_metadata ?? {};
      const metadataStartingCapital = metadata.starting_capital;
      setProfile({
        email: data.user.email ?? "",
        fullName:
          typeof metadata.full_name === "string" ? metadata.full_name : "",
        orgName: typeof metadata.org_name === "string" ? metadata.org_name : "",
        startingCapital:
          typeof metadataStartingCapital === "string"
            ? metadataStartingCapital
            : typeof metadataStartingCapital === "number"
              ? String(metadataStartingCapital)
            : null,
      });
      setLoading(false);
    });
  }, []);

  async function handleProfileSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setProfilePending(true);

    try {
      const supabase = createClient();
      const { data: currentUser } = await supabase.auth.getUser();
      const currentEmail = currentUser.user?.email ?? "";
      const emailChanged =
        profile.email.trim().toLowerCase() !== currentEmail.toLowerCase();

      const { error: metadataError } = await supabase.auth.updateUser({
        data: {
          full_name: profile.fullName.trim(),
          org_name: profile.orgName.trim(),
          ...(profile.startingCapital
            ? { starting_capital: profile.startingCapital }
            : {}),
        },
      });

      if (metadataError) {
        throw metadataError;
      }

      if (emailChanged) {
        const { error: emailError } = await supabase.auth.updateUser({
          email: profile.email.trim(),
        });

        if (emailError) {
          throw emailError;
        }

        toast.success("Profile saved. Confirm the email change from your inbox.");
      } else {
        toast.success("Profile updated.");
      }

      router.refresh();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Profile could not be saved.",
      );
    } finally {
      setProfilePending(false);
    }
  }

  async function handlePasswordSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (password.length < 8) {
      toast.error("Password must be at least 8 characters.");
      return;
    }

    if (password !== confirmPassword) {
      toast.error("Passwords do not match.");
      return;
    }

    setPasswordPending(true);

    try {
      const supabase = createClient();
      const { error } = await supabase.auth.updateUser({ password });

      if (error) {
        throw error;
      }

      setPassword("");
      setConfirmPassword("");
      toast.success("Password updated.");
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Password could not be updated.",
      );
    } finally {
      setPasswordPending(false);
    }
  }

  async function handleLogout() {
    setLogoutPending(true);

    try {
      const supabase = createClient();
      await supabase.auth.signOut();
      router.replace("/login");
      router.refresh();
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : "Could not sign out.",
      );
      setLogoutPending(false);
    }
  }

  if (loading) {
    return (
      <div className="mx-auto max-w-[720px]">
        <p className="text-sm text-zinc-500">Loading settings...</p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-[720px]">
      <section className="rounded-2xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap gap-2 border-b border-zinc-200 p-4 dark:border-zinc-800">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm ${
                activeTab === tab.key
                  ? "bg-zinc-950 font-medium text-white dark:bg-zinc-100 dark:text-zinc-950"
                  : "border border-zinc-200 bg-white text-zinc-600 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="p-6">
          {activeTab === "profile" && (
            <div>
              <h2 className="text-lg font-semibold">Profile</h2>
              <p className="mt-1 text-sm text-zinc-500">
                Your account details for this organization.
              </p>

              <form className="mt-5 space-y-4" onSubmit={handleProfileSubmit}>
                <FormField
                  label="Your name"
                  autoComplete="name"
                  required
                  value={profile.fullName}
                  onChange={(value) =>
                    setProfile((current) => ({ ...current, fullName: value }))
                  }
                />

                <FormField
                  label="Organization"
                  autoComplete="organization"
                  required
                  value={profile.orgName}
                  onChange={(value) =>
                    setProfile((current) => ({ ...current, orgName: value }))
                  }
                />

                <FormField
                  label="Email"
                  type="email"
                  autoComplete="email"
                  required
                  helper="Changing email sends a confirmation link."
                  value={profile.email}
                  onChange={(value) =>
                    setProfile((current) => ({ ...current, email: value }))
                  }
                />

                <button
                  type="submit"
                  disabled={profilePending}
                  className={buttonPrimaryClassName}
                >
                  {profilePending ? "Saving..." : "Save profile"}
                </button>
              </form>
            </div>
          )}

          {activeTab === "password" && (
            <div>
              <h2 className="text-lg font-semibold">Password</h2>
              <p className="mt-1 text-sm text-zinc-500">
                Set a new password for your account.
              </p>

              <form className="mt-5 space-y-4" onSubmit={handlePasswordSubmit}>
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
                  value={confirmPassword}
                  onChange={setConfirmPassword}
                />

                <button
                  type="submit"
                  disabled={passwordPending}
                  className={buttonPrimaryClassName}
                >
                  {passwordPending ? "Updating..." : "Change password"}
                </button>
              </form>
            </div>
          )}

          {activeTab === "session" && (
            <div>
              <h2 className="text-lg font-semibold">Session</h2>
              <p className="mt-1 text-sm text-zinc-500">
                Sign out of Pease Capital on this device.
              </p>

              <button
                type="button"
                onClick={handleLogout}
                disabled={logoutPending}
                className={`${buttonSecondaryClassName} mt-5`}
              >
                {logoutPending ? "Signing out..." : "Log out"}
              </button>
            </div>
          )}
        </div>
      </section>
    </div>
  );
}
