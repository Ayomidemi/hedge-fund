import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";

import {
  canAccessCapital,
  canAccessInvest,
  homePathForRole,
  resolvePeaseRole,
} from "@/lib/pease-role";

export async function updateSession(request: NextRequest) {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const anonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY;

  if (!url || !anonKey) {
    return NextResponse.next({ request });
  }

  let supabaseResponse = NextResponse.next({ request });

  const supabase = createServerClient(url, anonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(cookiesToSet) {
        cookiesToSet.forEach(({ name, value }) => {
          request.cookies.set(name, value);
        });
        supabaseResponse = NextResponse.next({ request });
        cookiesToSet.forEach(({ name, value, options }) => {
          supabaseResponse.cookies.set(name, value, options);
        });
      },
    },
  });

  const {
    data: { user },
  } = await supabase.auth.getUser();

  const pathname = request.nextUrl.pathname;
  const isAuthRoute =
    pathname.startsWith("/login") || pathname.startsWith("/auth/");

  if (!user && !isAuthRoute) {
    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = "/login";
    redirectUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(redirectUrl);
  }

  if (user && (pathname === "/login" || pathname.startsWith("/login/forgot-password"))) {
    const role = resolvePeaseRole(user);
    const redirectUrl = request.nextUrl.clone();
    redirectUrl.pathname = homePathForRole(role);
    redirectUrl.search = "";
    return NextResponse.redirect(redirectUrl);
  }

  if (user && !isAuthRoute) {
    const role = resolvePeaseRole(user);
    const onInvest = pathname === "/invest" || pathname.startsWith("/invest/");
    const onShared =
      pathname === "/settings" || pathname.startsWith("/settings/");
    const onCapital =
      !onInvest &&
      !onShared &&
      pathname !== "/login" &&
      !pathname.startsWith("/auth/") &&
      !pathname.startsWith("/_next");

    if (onInvest && !canAccessInvest(role)) {
      const redirectUrl = request.nextUrl.clone();
      redirectUrl.pathname = "/";
      redirectUrl.search = "";
      return NextResponse.redirect(redirectUrl);
    }

    if (onCapital && !canAccessCapital(role)) {
      const redirectUrl = request.nextUrl.clone();
      redirectUrl.pathname = "/invest";
      redirectUrl.search = "";
      return NextResponse.redirect(redirectUrl);
    }
  }

  return supabaseResponse;
}
