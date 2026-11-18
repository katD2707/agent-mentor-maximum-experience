// Fixed public address for a Mentor server that runs behind a Cloudflare quick tunnel (infra/share/README.md).
// A quick tunnel gets a new *.trycloudflare.com address at every start; share-up.ps1 writes it into KV ("target"), and
// the installers keep calling this worker's fixed workers.dev address. Every request (REST, SSE, WebSocket) is passed
// through unchanged.
export default {
  async fetch(request, env) {
    const target = await env.MENTOR.get("target", { cacheTtl: 30 });
    if (!target) return offline();
    const url = new URL(request.url);
    try {
      return await fetch(new Request(new URL(url.pathname + url.search, target), request));
    } catch {
      return offline();
    }
  },
};

function offline() {
  return new Response(JSON.stringify({ error: "server_offline" }), {
    status: 503,
    headers: { "content-type": "application/json", "retry-after": "60" },
  });
}
