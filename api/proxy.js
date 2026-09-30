const approvedRoute =
  /^\/api\/(session|health|login|logout|examples|jobs(?:\/[a-f0-9]{32}(?:\/(?:cancel|report))?)?|connections|reports\/[a-z-]+)$/;
const bodyLimit = 18000;

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
  const url = new URL(request.url);
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
    const response = await fetchUpstream(new URL(url.pathname, upstream), {
      method: request.method,
      headers,
      body,
      redirect: "manual",
      signal: AbortSignal.timeout(10000),
    });
    if (response.status >= 300 && response.status < 400)
      return json("Worker connector returned an unexpected redirect.", 502);
    const out = new Headers();
    for (const key of ["content-type", "content-disposition", "set-cookie"])
      if (response.headers.has(key)) out.set(key, response.headers.get(key));
    out.set("cache-control", "no-store");
    out.set("x-content-type-options", "nosniff");
    return new Response(response.body, {
      status: response.status,
      headers: out,
    });
  } catch {
    return json(
      "The local worker connector is unavailable. Published reports can still be explored.",
      503,
    );
  }
}

export default {
  fetch(request) {
    return proxy(request);
  },
};
