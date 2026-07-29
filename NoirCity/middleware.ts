import { createServerClient } from "@supabase/ssr";
import { NextResponse, type NextRequest } from "next/server";
import { SUPABASE_ANON_KEY, SUPABASE_URL, multiplayerConfigured } from "@/lib/supabase/env";

/**
 * Refreshes the Supabase session on every request.
 *
 * Without this, an anonymous token quietly expires part-way through a ninety
 * minute case and the next action comes back 401 - which reads to the player as
 * the game breaking for no reason.
 */
export async function middleware(request: NextRequest) {
  if (!multiplayerConfigured) return NextResponse.next();

  let response = NextResponse.next({ request });

  const supabase = createServerClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
    cookies: {
      getAll() {
        return request.cookies.getAll();
      },
      setAll(list) {
        for (const { name, value } of list) request.cookies.set(name, value);
        response = NextResponse.next({ request });
        for (const { name, value, options } of list) {
          response.cookies.set(name, value, options);
        }
      },
    },
  });

  // Touching getUser() is what actually performs the refresh.
  await supabase.auth.getUser();

  return response;
}

export const config = {
  matcher: [
    // Everything except static assets and the city geometry, which is a large
    // cacheable file that has no business round-tripping through auth.
    "/((?!_next/static|_next/image|favicon.ico|city.json|.*\\.(?:png|jpg|jpeg|gif|webp|svg|woff2?)$).*)",
  ],
};
