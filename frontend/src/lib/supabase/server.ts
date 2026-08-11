import "server-only";

import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

export async function createClient() {
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
}

export async function getServerAccessToken(): Promise<string | undefined> {
  const supabase = await createClient();
  const { data: userData, error: userError } = await supabase.auth.getUser();

  if (userError || !userData.user) {
    return undefined;
  }

  const { data: sessionData } = await supabase.auth.getSession();
  return sessionData.session?.access_token;
}

export async function getServerUserEmail(): Promise<string | null> {
  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();
  return data.user?.email ?? null;
}

export async function getServerUserProfile(): Promise<{
  email: string | null;
  fullName: string | null;
  orgName: string | null;
}> {
  const supabase = await createClient();
  const { data } = await supabase.auth.getUser();
  const metadata = data.user?.user_metadata ?? {};

  return {
    email: data.user?.email ?? null,
    fullName: typeof metadata.full_name === "string" ? metadata.full_name : null,
    orgName: typeof metadata.org_name === "string" ? metadata.org_name : null,
  };
}
