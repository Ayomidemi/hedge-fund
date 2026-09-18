"use client";

import { useState } from "react";
import Link from "next/link";
import { buttonSecondaryClassName } from "@/components/ui/form-styles";
import { money } from "@/components/invest/format";
import type { InvestProfile, InvestProfilePermission } from "@/lib/api";

type ProfileTab = "account" | "access";

const tabs: { key: ProfileTab; label: string }[] = [
  { key: "account", label: "Account" },
  { key: "access", label: "Access" },
];

export function InvestProfileTabs({ profile }: { profile: InvestProfile }) {
  const [activeTab, setActiveTab] = useState<ProfileTab>("account");

  return (
    <div className="mx-auto max-w-[760px]">
      <section className="rounded-2xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
        <div className="flex flex-wrap items-start justify-between gap-4 border-b border-zinc-200 p-5 dark:border-zinc-800">
          <div>
            <p className="text-xs uppercase tracking-wide text-zinc-500">
              Pease Invest
            </p>
            <h2 className="mt-1 text-xl font-semibold">
              {profile.full_name ?? profile.email ?? "Invest user"}
            </h2>
            <p className="mt-1 text-sm text-zinc-500">
              {profile.account.account_number}
            </p>
          </div>
          <Link href="/invest/activity" className={buttonSecondaryClassName}>
            Activity
          </Link>
        </div>

        <div className="flex flex-wrap gap-2 border-b border-zinc-200 p-4 dark:border-zinc-800">
          {tabs.map((tab) => (
            <button
              key={tab.key}
              type="button"
              onClick={() => setActiveTab(tab.key)}
              className={`whitespace-nowrap rounded-lg px-3 py-2 text-sm ${
                activeTab === tab.key
                  ? "bg-emerald-800 font-medium text-white"
                  : "border border-zinc-200 bg-white text-zinc-600 dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400"
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        <div className="p-6">
          {activeTab === "account" ? <AccountTab profile={profile} /> : null}
          {activeTab === "access" ? <AccessTab profile={profile} /> : null}
        </div>
      </section>
    </div>
  );
}

function AccountTab({ profile }: { profile: InvestProfile }) {
  return (
    <div>
      <h3 className="text-lg font-semibold">Account</h3>
      <div className="mt-5 grid gap-3 sm:grid-cols-3">
        <Metric
          label="Cash"
          value={money(profile.account.cash, profile.account.base_currency)}
        />
        <Metric
          label="Buying power"
          value={money(profile.account.buying_power, profile.account.base_currency)}
        />
        <Metric
          label="Status"
          value={profile.account.status.replaceAll("_", " ")}
        />
      </div>
      <dl className="mt-5 grid gap-3 text-sm sm:grid-cols-2">
        <Detail label="Broker" value={profile.account.broker_provider} />
        <Detail label="Currency" value={profile.account.base_currency} />
        <Detail label="Role" value={profile.role ?? "standard access"} />
        <Detail
          label="Created"
          value={new Date(profile.account.created_at).toLocaleDateString()}
        />
      </dl>
      <div className="mt-5 flex flex-wrap gap-2">
        <Link href="/settings" className={buttonSecondaryClassName}>
          Account settings
        </Link>
        <Link href="/invest/cash" className={buttonSecondaryClassName}>
          Cash
        </Link>
      </div>
    </div>
  );
}

function AccessTab({ profile }: { profile: InvestProfile }) {
  return (
    <div>
      <h3 className="text-lg font-semibold">Access</h3>
      <div className="mt-5 divide-y divide-zinc-100 rounded-xl border border-zinc-200 dark:divide-zinc-900 dark:border-zinc-800">
        {profile.permissions.map((permission) => (
          <PermissionRow key={permission.code} permission={permission} />
        ))}
      </div>
      <div className="mt-5">
        <p className="text-sm font-medium">Alerts</p>
        <div className="mt-3 flex flex-wrap gap-2">
          {profile.notification_settings.map((item) => (
            <span
              key={item}
              className="rounded-md bg-zinc-100 px-2 py-1 text-xs text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300"
            >
              {item}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-zinc-50 p-4 dark:bg-zinc-900">
      <p className="text-xs uppercase tracking-wide text-zinc-500">{label}</p>
      <p className="mt-1 font-semibold capitalize tabular-nums">{value}</p>
    </div>
  );
}

function Detail({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-zinc-500">{label}</dt>
      <dd className="mt-1 font-medium capitalize">{value.replaceAll("_", " ")}</dd>
    </div>
  );
}

function PermissionRow({
  permission,
}: {
  permission: InvestProfilePermission;
}) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
      <div>
        <p className="font-medium">{permission.label}</p>
        <p className="mt-1 text-xs text-zinc-500">{permission.description}</p>
      </div>
      <span
        className={`rounded-md px-2 py-1 text-xs font-medium ${
          permission.enabled
            ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-200"
            : "bg-zinc-100 text-zinc-600 dark:bg-zinc-900 dark:text-zinc-300"
        }`}
      >
        {permission.enabled ? "On" : "Off"}
      </span>
    </div>
  );
}
