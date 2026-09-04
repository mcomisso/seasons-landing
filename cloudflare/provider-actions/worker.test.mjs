import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import worker from "./worker.mjs";

const ENV = {
  SEASONS_PROVIDER_ACTIONS_MODE: "proxy",
  SEASONS_PROVIDER_ACTIONS_ORIGIN: "https://api.getseasons.app",
};

const ORIGIN_HEADERS = {
  "Cache-Control": "no-store",
  "Content-Security-Policy":
    "default-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
  "Content-Type": "text/html; charset=utf-8",
  "Referrer-Policy": "no-referrer",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "DENY",
  "X-Robots-Tag": "noindex",
};

test("proxies the exact Provider Actions URL without forwarding private headers", async () => {
  const observed = [];
  const response = await worker.fetch(
    new Request(
      "https://getseasons.app/provider-actions/start/8/GB/?source=plan%2Fswitch",
      {
        headers: {
          Accept: "text/html",
          Authorization: "Bearer must-not-cross-public-boundary",
          Cookie: "session=must-not-cross-public-boundary",
        },
      }
    ),
    ENV,
    {
      fetch: async (request) => {
        observed.push(request);
        return new Response(null, {
          status: 302,
          headers: {
            ...ORIGIN_HEADERS,
            Location: "https://www.netflix.com/",
            "X-Seasons-Provider-Actions-Release": "release-42",
          },
        });
      },
    }
  );

  assert.equal(observed.length, 1);
  assert.equal(
    observed[0].url,
    "https://api.getseasons.app/provider-actions/start/8/GB/?source=plan%2Fswitch"
  );
  assert.equal(observed[0].method, "GET");
  assert.equal(observed[0].headers.get("accept"), "text/html");
  assert.equal(observed[0].headers.get("authorization"), null);
  assert.equal(observed[0].headers.get("cookie"), null);
  assert.equal(observed[0].redirect, "manual");
  assert.equal(response.status, 302);
  assert.equal(response.headers.get("location"), "https://www.netflix.com/");
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(
    response.headers.get("x-seasons-provider-actions-release"),
    "release-42"
  );
});

test("preserves encoded raw path and query bytes for backend validation", async () => {
  let target;
  await worker.fetch(
    new Request(
      "https://getseasons.app/provider-actions/start%2F8%2FGB%2F?x=%2f&x=%2F"
    ),
    ENV,
    {
      fetch: async (request) => {
        target = request.url;
        return new Response("safe", { status: 400, headers: ORIGIN_HEADERS });
      },
    }
  );

  assert.equal(
    target,
    "https://api.getseasons.app/provider-actions/start%2F8%2FGB%2F?x=%2f&x=%2F"
  );
});

for (const url of [
  "https://getseasons.app/",
  "https://getseasons.app/provider-action/start/8/GB/",
  "https://www.getseasons.app/provider-actions/start/8/GB/",
  "https://example.com/provider-actions/start/8/GB/",
]) {
  test(`fails closed without proxying unrelated request ${url}`, async () => {
    let fetchCalled = false;
    const response = await worker.fetch(new Request(url), ENV, {
      fetch: async () => {
        fetchCalled = true;
        return new Response("unexpected");
      },
    });

    assert.equal(fetchCalled, false);
    assert.equal(response.status, 404);
    assert.equal(response.headers.get("cache-control"), "no-store");
    assert.equal(response.headers.get("x-robots-tag"), "noindex");
  });
}

for (const origin of [
  "http://api.getseasons.app",
  "https://api.getseasons.app/extra",
  "https://api.getseasons.app?route=other",
  "https://api.getseasons.app:443",
  "https://API.getseasons.app",
  "https://example.com",
  "",
]) {
  test(`rejects noncanonical backend origin ${origin || "<empty>"}`, async () => {
    let fetchCalled = false;
    const response = await worker.fetch(
      new Request("https://getseasons.app/provider-actions/start/8/GB/"),
      { ...ENV, SEASONS_PROVIDER_ACTIONS_ORIGIN: origin },
      {
        fetch: async () => {
          fetchCalled = true;
          return new Response("unexpected");
        },
      }
    );

    assert.equal(fetchCalled, false);
    assert.equal(response.status, 503);
    assert.equal(response.headers.get("cache-control"), "no-store");
    assert.match(await response.text(), /temporarily unavailable/i);
  });
}

test("rejects mutating methods without contacting the backend", async () => {
  let fetchCalled = false;
  const response = await worker.fetch(
    new Request("https://getseasons.app/provider-actions/start/8/GB/", {
      method: "POST",
    }),
    ENV,
    {
      fetch: async () => {
        fetchCalled = true;
        return new Response("unexpected");
      },
    }
  );

  assert.equal(fetchCalled, false);
  assert.equal(response.status, 405);
  assert.equal(response.headers.get("allow"), "GET");
  assert.equal(response.headers.get("cache-control"), "no-store");
});

test("safe-baseline mode keeps canonical links usable without origin traffic", async () => {
  let fetchCalled = false;
  const response = await worker.fetch(
    new Request("https://getseasons.app/provider-actions/cancel/8/GB/"),
    { ...ENV, SEASONS_PROVIDER_ACTIONS_MODE: "safe-baseline" },
    {
      fetch: async () => {
        fetchCalled = true;
        return new Response("unexpected");
      },
    }
  );

  assert.equal(fetchCalled, false);
  assert.equal(response.status, 503);
  assert.equal(response.headers.get("cache-control"), "no-store");
  const body = await response.text();
  assert.match(body, /<main>/);
  assert.match(body, /<h1>Provider Actions are temporarily unavailable<\/h1>/);
  assert.match(body, /No subscription state has changed\./);
  assert.match(body, /href="https:\/\/getseasons\.app\/"/);
});

test("origin failure returns the accessible safe response", async () => {
  const response = await worker.fetch(
    new Request("https://getseasons.app/provider-actions/cancel/8/GB/"),
    ENV,
    {
      fetch: async () => {
        throw new Error("origin unavailable");
      },
    }
  );

  assert.equal(response.status, 503);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(response.headers.get("x-robots-tag"), "noindex");
  assert.match(await response.text(), /temporarily unavailable/i);
});

for (const unsafeResponse of [
  new Response("stale", { status: 200 }),
  new Response("server error", { status: 500, headers: ORIGIN_HEADERS }),
  new Response("cached", {
    status: 200,
    headers: { ...ORIGIN_HEADERS, "Cache-Control": "public, max-age=3600" },
  }),
]) {
  test(`fails closed for unsafe backend response ${unsafeResponse.status}`, async () => {
    const response = await worker.fetch(
      new Request("https://getseasons.app/provider-actions/cancel/8/GB/"),
      ENV,
      { fetch: async () => unsafeResponse.clone() }
    );

    assert.equal(response.status, 502);
    assert.equal(response.headers.get("cache-control"), "no-store");
    assert.match(await response.text(), /temporarily unavailable/i);
  });
}

test("removes origin cookies while preserving verified response bytes", async () => {
  const response = await worker.fetch(
    new Request("https://getseasons.app/provider-actions/cancel/8/GB/"),
    ENV,
    {
      fetch: async () =>
        new Response("<main><h1>Cancel Netflix</h1></main>", {
          status: 200,
          headers: { ...ORIGIN_HEADERS, "Set-Cookie": "private=value" },
        }),
    }
  );

  assert.equal(response.status, 200);
  assert.equal(response.headers.get("set-cookie"), null);
  assert.equal(
    await response.text(),
    "<main><h1>Cancel Netflix</h1></main>"
  );
});

test("replaces permissive origin security headers with the public safe policy", async () => {
  const response = await worker.fetch(
    new Request("https://getseasons.app/provider-actions/cancel/8/GB/"),
    ENV,
    {
      fetch: async () =>
        new Response("safe body", {
          status: 200,
          headers: {
            ...ORIGIN_HEADERS,
            "Content-Security-Policy": "default-src *; frame-ancestors *",
            "Referrer-Policy": "unsafe-url",
            "X-Content-Type-Options": "off",
            "X-Frame-Options": "ALLOWALL",
          },
        }),
    }
  );

  assert.equal(
    response.headers.get("content-security-policy"),
    "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
  );
  assert.equal(response.headers.get("referrer-policy"), "no-referrer");
  assert.equal(response.headers.get("x-content-type-options"), "nosniff");
  assert.equal(response.headers.get("x-frame-options"), "DENY");
});

test("Cloudflare configs capture only the Provider Actions route family", async () => {
  for (const [name, expectedMode] of [
    ["wrangler.toml", "proxy"],
    ["wrangler.safe-baseline.toml", "safe-baseline"],
  ]) {
    const config = await readFile(new URL(`./${name}`, import.meta.url), "utf8");

    assert.match(config, /name = "seasons-provider-actions-router"/);
    assert.match(config, /pattern = "getseasons\.app\/provider-actions"/);
    assert.match(config, /pattern = "getseasons\.app\/provider-actions\/\*"/);
    assert.doesNotMatch(config, /pattern = "getseasons\.app\/\*"/);
    assert.doesNotMatch(config, /pattern = "\*getseasons\.app/);
    assert.match(
      config,
      /SEASONS_PROVIDER_ACTIONS_ORIGIN = "https:\/\/api\.getseasons\.app"/
    );
    assert.match(
      config,
      new RegExp(`SEASONS_PROVIDER_ACTIONS_MODE = "${expectedMode}"`)
    );
  }
});
