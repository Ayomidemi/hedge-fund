import "server-only";

import { cache } from "react";
import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import type { User } from "@supabase/supabase-js";

export const createClient = cache(async () => {
  const cookieStore = await cookies();
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !anonKey) {
    throw new Error(
      "Missing NEXT_PUBLIC_SUPABASE_URL or NEXT_PUBLIC_SUPABASE_ANON_KEY.",
    );
  }

  return createServerClient(url, anonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => {
            cookieStore.set(name, value, options);
          });
        } catch {
          // Server Components cannot always mutate cookies.
        }
      },
    },
  });
});

const getServerAuth = cache(async () => {
  const supabase = await createClient();
  const { data: userData, error: userError } = await supabase.auth.getUser();
  if (userError || !userData.user) {
    return { user: null as User | null, accessToken: undefined as string | undefined };
  }
  const { data: sessionData } = await supabase.auth.getSession();
  return {
    user: userData.user,
    accessToken: sessionData.session?.access_token,
  };
});

export async function getServerAccessToken(): Promise<string | undefined> {
  const auth = await getServerAuth();
  return auth.accessToken;
}

export async function getServerUserEmail(): Promise<string | null> {
  const auth = await getServerAuth();
  return auth.user?.email ?? null;
}

export async function getServerUserProfile(): Promise<{
  email: string | null;
  fullName: string | null;
  orgName: string | null;
  role: string | null;
  canSwitchProducts: boolean;
}> {
  const auth = await getServerAuth();
  const { resolvePeaseRole, canSwitchProducts } = await import("@/lib/pease-role");
  const metadata = auth.user?.user_metadata ?? {};
  const role = resolvePeaseRole(auth.user);

  return {
    email: auth.user?.email ?? null,
    fullName: typeof metadata.full_name === "string" ? metadata.full_name : null,
    orgName: typeof metadata.org_name === "string" ? metadata.org_name : null,
    role,
    canSwitchProducts: canSwitchProducts(role),
  };
}
