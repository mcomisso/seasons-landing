const PUBLIC_ORIGIN = "https://getseasons.app";
const BACKEND_ORIGIN = "https://api.getseasons.app";
const STAGING_HOST =
  /^seasons-provider-actions-router-staging\.[a-z0-9-]+\.workers\.dev$/;
const SAFE_ORIGIN_STATUSES = new Set([200, 302, 400, 404]);
const RELEASE_HEADER = "X-Seasons-Provider-Actions-Release";
const REGION_HEADER = "X-Seasons-Provider-Actions-Region";
const PROVIDER_HEADER = "X-Seasons-Provider-Actions-Provider";
const CANONICAL_ACTION_PATH =
  /^\/provider-actions\/(?:cancel|start)\/([1-9][0-9]*)\/([A-Z]{2})\/$/;

const SAFE_HEADERS = {
  "Cache-Control": "no-store",
  "Content-Security-Policy":
    "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
  "Content-Type": "text/html; charset=utf-8",
  "Permissions-Policy":
    "camera=(), geolocation=(), microphone=(), payment=(), usb=()",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "X-Robots-Tag": "noindex",
};

const REQUIRED_ORIGIN_HEADERS = [
  "content-security-policy",
  "referrer-policy",
  "x-content-type-options",
  "x-frame-options",
  "x-robots-tag",
];

function safeResponse(status, heading, message, extraHeaders = {}) {
  const body = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>${heading} - Seasons</title>
</head>
<body>
<main>
<h1>${heading}</h1>
<p>${message}</p>
<p>No subscription state has changed.</p>
<a href="https://getseasons.app/">Open Seasons</a>
</main>
</body>
</html>
`;
  return new Response(body, {
    status,
    headers: { ...SAFE_HEADERS, ...extraHeaders },
  });
}

function configuredBackendOrigin(env) {
  const value = env?.SEASONS_PROVIDER_ACTIONS_ORIGIN;
  if (value !== BACKEND_ORIGIN && value !== `${BACKEND_ORIGIN}/`) {
    return null;
  }

  try {
    const origin = new URL(value);
    if (
      origin.origin !== BACKEND_ORIGIN ||
      origin.pathname !== "/" ||
      origin.search !== "" ||
      origin.hash !== "" ||
      origin.username !== "" ||
      origin.password !== ""
    ) {
      return null;
    }
    return BACKEND_ORIGIN;
  } catch {
    return null;
  }
}

function isProviderActionsRequest(url, mode) {
  const acceptedOrigin =
    url.origin === PUBLIC_ORIGIN ||
    (mode === "staging-proxy" &&
      url.protocol === "https:" &&
      url.port === "" &&
      STAGING_HOST.test(url.hostname));
  return (
    acceptedOrigin &&
    (url.pathname === "/provider-actions" ||
      url.pathname.startsWith("/provider-actions/"))
  );
}

function expectedContentType(pathname, status) {
  return pathname === "/provider-actions/sitemap.xml" && status === 200
    ? "application/xml; charset=utf-8"
    : "text/html; charset=utf-8";
}

function hasSafeOriginResponse(response, pathname) {
  if (
    !SAFE_ORIGIN_STATUSES.has(response.status) ||
    response.headers.get("cache-control") !== "no-store" ||
    response.headers.get("content-type") !==
      expectedContentType(pathname, response.status) ||
    REQUIRED_ORIGIN_HEADERS.some((name) => !response.headers.has(name)) ||
    !response.headers.get(RELEASE_HEADER) ||
    (response.status === 302 && !response.headers.get("Location"))
  ) {
    return false;
  }

  const pair = pathname.match(CANONICAL_ACTION_PATH);
  if (pair === null) {
    return true;
  }
  return (
    response.headers.get(PROVIDER_HEADER) === pair[1] &&
    response.headers.get(REGION_HEADER) === pair[2]
  );
}

function publicResponse(response, pathname) {
  const headers = new Headers(SAFE_HEADERS);
  for (const name of [RELEASE_HEADER, REGION_HEADER, PROVIDER_HEADER]) {
    const value = response.headers.get(name);
    if (value !== null) {
      headers.set(name, value);
    }
  }
  headers.set("Content-Type", expectedContentType(pathname, response.status));
  if (response.status === 302) {
    headers.set("Location", response.headers.get("Location"));
  }
  return new Response(response.body, {
    status: response.status,
    statusText: response.statusText,
    headers,
  });
}

export default {
  async fetch(request, env, executionContext) {
    const incoming = new URL(request.url);
    const mode = env?.SEASONS_PROVIDER_ACTIONS_MODE;
    if (!isProviderActionsRequest(incoming, mode)) {
      return safeResponse(404, "Not found", "This page does not exist.");
    }
    if (request.method !== "GET") {
      return safeResponse(
        405,
        "Method not allowed",
        "Provider Actions accept browser navigation requests only.",
        { Allow: "GET" }
      );
    }
    if (mode === "safe-baseline") {
      return safeResponse(
        503,
        "Provider Actions are temporarily unavailable",
        "Try again later or return to Seasons."
      );
    }
    if (mode !== "proxy" && mode !== "staging-proxy") {
      return safeResponse(
        503,
        "Provider Actions are temporarily unavailable",
        "The public route is not active."
      );
    }

    const backendOrigin = configuredBackendOrigin(env);
    if (backendOrigin === null) {
      return safeResponse(
        503,
        "Provider Actions are temporarily unavailable",
        "The service configuration is invalid."
      );
    }

    const rawPathAndQuery = request.url.slice(incoming.origin.length);
    const headers = new Headers();
    const accept = request.headers.get("Accept");
    if (accept !== null) {
      headers.set("Accept", accept);
    }
    const backendRequest = new Request(`${backendOrigin}${rawPathAndQuery}`, {
      method: "GET",
      headers,
      redirect: "manual",
    });
    const fetchOrigin = executionContext?.fetch ?? globalThis.fetch;

    try {
      const response = await fetchOrigin(backendRequest);
      if (!hasSafeOriginResponse(response, incoming.pathname)) {
        return safeResponse(
          502,
          "Provider Actions are temporarily unavailable",
          "The service returned an unsafe response."
        );
      }
      return publicResponse(response, incoming.pathname);
    } catch {
      return safeResponse(
        503,
        "Provider Actions are temporarily unavailable",
        "The service could not be reached."
      );
    }
  },
};
