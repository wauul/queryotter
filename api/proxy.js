import {
  monitoredProxy,
  captureProxy,
  upstreamTraceHeaders,
} from "./monitoring.js";

const approvedRoute =
  /^\/api\/(session|health|login|logout|examples|jobs(?:\/[a-f0-9]{32}(?:\/(?:cancel|report))?)?|connections|reports\/[a-z-]+|assistant\/(?:catalog|session|settings|logout|parse-connection|demo\/start|auth\/(?:github|google|microsoft)\/(?:start|callback)|auth\/owner|connections(?:\/demo|\/[a-f0-9]{32}\/(?:remove|rotate|prisma|schema))?|jobs(?:\/[a-f0-9]{32}(?:\/cancel)?)?|results\/[a-f0-9]{32}(?:\/export)?|history(?:\/clear|\/[a-f0-9]{32}\/export)?|saved(?:\/[a-f0-9]{32}\/remove)?|account\/(?:export|delete)|connectors(?:\/[a-f0-9]{32}\/(?:remove|poll|complete))?))$/;

function json(detail, status) {
  return Response.json(
    { detail },
    {
      status,
      headers: {
        "cache-control": "no-store",
        "x-content-type-options": "nosniff",
      },
    },
  );
}

// A short-lived HTTP proxy only. Investigations stay in the durable Python worker.
export async function proxy(request, env = process.env, fetchUpstream = fetch) {
  return monitoredProxy(request, () => forward(request, env, fetchUpstream));
}

async function forward(request, env, fetchUpstream) {
  const url = new URL(request.url);
  const bodyLimit =
    url.pathname.startsWith("/api/assistant/connections") ||
    /\/connectors\/[a-f0-9]{32}\/complete$/.test(url.pathname)
      ? 3000000
      : url.pathname.startsWith("/api/assistant/")
        ? 65536
        : 18000;
  if (!approvedRoute.test(url.pathname)) return json("Not found", 404);
  if (!["GET", "POST"].includes(request.method))
    return json("Method not allowed", 405);
  const origin = request.headers.get("origin");
  if (request.method === "POST" && origin && origin !== url.origin)
    return json("Cross-origin writes forbidden", 403);
  if (Number(request.headers.get("content-length") || 0) > bodyLimit)
    return json("Request too large", 413);
  if (!env.CONNECTOR_URL || !env.SERVICE_TOKEN)
    return json(
      "Worker connector is offline. Published measured reports remain available.",
      503,
    );

  let body;
  if (request.method === "POST") {
    // Count actual bytes too: Content-Length can be absent or misleading.
    const reader = request.body?.getReader();
    const chunks = [];
    let size = 0;
    if (reader) {
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        size += value.byteLength;
        if (size > bodyLimit) {
          await reader.cancel();
          return json("Request too large", 413);
        }
        chunks.push(value);
      }
    }
    body = new Uint8Array(size);
    let offset = 0;
    for (const chunk of chunks) {
      body.set(chunk, offset);
      offset += chunk.byteLength;
    }
  }

  const headers = new Headers();
  for (const key of ["content-type", "cookie", "origin"])
    if (request.headers.has(key)) headers.set(key, request.headers.get(key));
  if (
    /\/connectors\/[a-f0-9]{32}\/(poll|complete)$/.test(url.pathname) &&
    request.headers.has("authorization")
  )
    headers.set("authorization", request.headers.get("authorization"));
  headers.set("x-service-token", env.SERVICE_TOKEN);
  headers.set("x-app-origin", url.origin);
  headers.set("x-forwarded-proto", "https");
  try {
    const upstream = new URL(env.CONNECTOR_URL);
    if (
      upstream.protocol !== "https:" ||
      upstream.username ||
      upstream.password
    )
      return json("Worker connector configuration is invalid.", 503);
    // CONNECTOR_URL is the operator-approved destination. Never follow redirects
    // or propagate third-party baggage to arbitrary user-selected databases.
    for (const [key, value] of Object.entries(
      upstreamTraceHeaders(request.headers),
    ))
      headers.set(key, value);
    const response = await fetchUpstream(
      new URL(url.pathname + url.search, upstream),
      {
        method: request.method,
        headers,
        body,
        redirect: "manual",
        signal: AbortSignal.timeout(
          url.pathname.endsWith("/callback") ? 50000 : 10000,
        ),
      },
    );
    if (response.status >= 300 && response.status < 400)
      return json("Worker connector returned an unexpected redirect.", 502);
    const out = new Headers();
    for (const key of [
      "content-type",
      "content-disposition",
      "content-security-policy",
      "referrer-policy",
    ])
      if (response.headers.has(key)) out.set(key, response.headers.get(key));
    for (const cookie of response.headers.getSetCookie())
      out.append("set-cookie", cookie);
    out.set("cache-control", "no-store");
    out.set("x-content-type-options", "nosniff");
    return new Response(response.body, {
      status: response.status,
      headers: out,
    });
  } catch (error) {
    captureProxy(error);
    return json(
      "The investigation service is unavailable. Published reports can still be explored.",
      503,
    );
  }
}

export default {
  fetch(request) {
    return proxy(request);
  },
};
