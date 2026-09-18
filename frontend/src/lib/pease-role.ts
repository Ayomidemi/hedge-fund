export type PeaseProductRole =
  | "ADMIN"
  | "CAPITAL_PM"
  | "CAPITAL_ANALYST"
  | "CAPITAL_RISK"
  | "RETAIL_USER";

export const SIGNUP_PRODUCT_ROLES = [
  {
    value: "CAPITAL_PM" as const,
    label: "Pease Capital",
    hint: "Fund desk — research, risk, and portfolio control.",
  },
  {
    value: "RETAIL_USER" as const,
    label: "Pease Invest",
    hint: "",
  },
];

const RETAIL_ROLES = new Set(["RETAIL_USER"]);
const CAPITAL_ROLES = new Set([
  "CAPITAL_PM",
  "CAPITAL_ANALYST",
  "CAPITAL_RISK",
]);
const ADMIN_ROLES = new Set(["ADMIN"]);
const PRODUCT_ROLES = new Set([
  ...RETAIL_ROLES,
  ...CAPITAL_ROLES,
  ...ADMIN_ROLES,
]);

export function normalizePeaseRole(value: unknown): PeaseProductRole | null {
  const role = String(value ?? "")
    .trim()
    .toUpperCase();
  if (PRODUCT_ROLES.has(role)) {
    return role as PeaseProductRole;
  }
  return null;
}

export function resolvePeaseRole(user: {
  app_metadata?: Record<string, unknown> | null;
  user_metadata?: Record<string, unknown> | null;
} | null | undefined): PeaseProductRole | null {
  if (!user) return null;
  const app = user.app_metadata ?? {};
  const meta = user.user_metadata ?? {};
  for (const candidate of [
    app.pease_role,
    app.role,
    meta.pease_role,
    meta.role,
  ]) {
    const role = normalizePeaseRole(candidate);
    if (role) return role;
  }
  return null;
}

export function canAccessCapital(role: PeaseProductRole | null): boolean {
  return !role || !RETAIL_ROLES.has(role);
}

export function canAccessInvest(role: PeaseProductRole | null): boolean {
  return !role || !CAPITAL_ROLES.has(role);
}

export function canSwitchProducts(role: PeaseProductRole | null): boolean {
  return role !== null && ADMIN_ROLES.has(role);
}

export function homePathForRole(role: PeaseProductRole | null): string {
  if (role && RETAIL_ROLES.has(role)) return "/invest";
  return "/";
}
