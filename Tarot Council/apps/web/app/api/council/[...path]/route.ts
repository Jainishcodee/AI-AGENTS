/**
 * Transparent proxy to the Python reasoning core.
 *
 * The browser never talks to FastAPI directly. That buys three things: a single
 * origin (so the streaming POST needs no CORS preflight, which is where SSE-over-
 * POST usually breaks), no API URL in the client bundle, and one place to add auth
 * in Phase 2. The cost is one extra hop on localhost.
 *
 * Streaming responses are piped straight through — `duplex: "half"` and no
 * buffering, so events reach the browser as the council emits them.
 */

const API = process.env.COUNCIL_API_URL ?? "http://127.0.0.1:8787";

async function forward(request: Request, path: string[]): Promise<Response> {
  const incoming = new URL(request.url);
  const target = `${API}/${path.join("/")}${incoming.search}`;

  const headers = new Headers();
  const contentType = request.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  headers.set("accept", request.headers.get("accept") ?? "application/json");

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: request.method,
      headers,
      body: request.method === "GET" || request.method === "HEAD" ? undefined : request.body,
      // Required by undici when streaming a request body.
      duplex: "half",
      cache: "no-store",
      signal: request.signal,
    } as RequestInit & { duplex: "half" });
  } catch (error) {
    return Response.json(
      {
        detail:
          `Cannot reach the reasoning core at ${API}. Start it with ` +
          `\`uvicorn app.main:app --port 8787\` from apps/api.`,
        cause: String(error),
      },
      { status: 503 },
    );
  }

  const responseHeaders = new Headers();
  for (const key of ["content-type", "cache-control"]) {
    const value = upstream.headers.get(key);
    if (value) responseHeaders.set(key, value);
  }
  // Stops any intermediary from buffering the event stream into one chunk.
  responseHeaders.set("x-accel-buffering", "no");

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export async function GET(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  return forward(request, (await ctx.params).path);
}

export async function POST(request: Request, ctx: { params: Promise<{ path: string[] }> }) {
  return forward(request, (await ctx.params).path);
}

export const dynamic = "force-dynamic";
export const runtime = "nodejs";
