// Cloudflare Email Worker: hands every message for <code>@<INBOUND_EMAIL_DOMAIN> to the mentor gateway.
//
//   Cloudflare Email Routing (catch-all -> "Send to a Worker") -> this Worker
//   -> POST $MENTOR_WEBHOOK_URL (https://<DOMAIN>/webhooks/email/inbound), body = the raw RFC 822 message.
//
// No dependencies (Web Crypto only). Setup, step by step: README.md, "Chuyển tiếp email của học viên".
//
// Bindings (Worker -> Settings -> Variables and Secrets, or wrangler.toml + `wrangler secret put`):
//   MENTOR_WEBHOOK_URL    plain text, e.g. https://mentor.example.vn/webhooks/email/inbound
//   EMAIL_WEBHOOK_SECRET  secret, the same value as EMAIL_WEBHOOK_SECRET in infra/.env.prod on the VM
//
// Request headers (CONTRACTS.md section 5):
//   X-Mentor-Rcpt        envelope recipient (message.to)
//   X-Mentor-Timestamp   unix seconds; the gateway refuses more than 5 minutes of clock difference
//   X-Mentor-Signature   "v1=" + hex(HMAC-SHA256(secret, "v1\n" + timestamp + "\n" + rcpt + "\n" + raw bytes))
// Test vector (same as services/gateway/tests/test_gw_email_webhook.py): secret "s3cret", timestamp "1761620400",
// rcpt "abc@inbox.example.vn", body "Subject: x\r\n\r\nhi" ->
//   v1=6d57ef202c587f48a250e7a5c9de1776ee1c42da33167d90558f58c98d67da77
//
// What the sender sees, by gateway answer:
//   2xx (stored, or no learner has this address: the gateway answers alike, so addresses cannot be probed)
//        -> accepted.
//   413 (too large) or 400 (malformed recipient) -> message.setReject(...): a permanent bounce with a reason.
//   anything else (429 rate limit, 401/404 wrong or missing secret, 5xx, network error, timeout)
//        -> the Worker throws. Cloudflare's docs do not say how a thrown error is reported to the sending server;
//           it is expected to be a temporary failure that the sender retries for hours to days, which gives time
//           to fix the gateway without losing mail. If it ever turns out to bounce, the sender still gets an
//           error message, nothing is silently lost.
// Logs (Workers Logs) carry the status and size only, never addresses or content.

const MAX_BYTES = 25 * 1024 * 1024; // Email Routing's own inbound limit (25 MiB); the gateway's cap is the same
const TIMEOUT_MS = 60_000;

const encoder = new TextEncoder();

function hex(buffer) {
  return [...new Uint8Array(buffer)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function signRequest(secret, timestamp, rcpt, raw) {
  const key = await crypto.subtle.importKey(
    "raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"],
  );
  const prefix = encoder.encode(`v1\n${timestamp}\n${rcpt}\n`);
  const data = new Uint8Array(prefix.length + raw.length);
  data.set(prefix, 0);
  data.set(raw, prefix.length);
  return "v1=" + hex(await crypto.subtle.sign("HMAC", key, data));
}

export default {
  async email(message, env, ctx) {
    const url = env.MENTOR_WEBHOOK_URL;
    const secret = env.EMAIL_WEBHOOK_SECRET;
    if (!url || !secret) {
      // configuration error: do not bounce, let the sender retry once it is fixed
      throw new Error("MENTOR_WEBHOOK_URL / EMAIL_WEBHOOK_SECRET not set on the Worker");
    }
    if (message.rawSize > MAX_BYTES) {
      message.setReject("Message too large (limit 25 MB including attachments)");
      return;
    }
    const rcpt = String(message.to || "").trim();
    if (!/^[\x21-\x7e]+@[\x21-\x7e]+$/.test(rcpt)) {
      // non-ASCII or odd recipient: cannot be a learner address (codes are ASCII). Accept and drop, like the
      // gateway does for unknown addresses, so nothing reveals which addresses exist.
      console.log(JSON.stringify({ event: "dropped", reason: "recipient not ascii", size: message.rawSize }));
      return;
    }

    const raw = new Uint8Array(await new Response(message.raw).arrayBuffer());
    const timestamp = Math.floor(Date.now() / 1000).toString();
    const signature = await signRequest(secret, timestamp, rcpt, raw);

    let response;
    try {
      response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "message/rfc822",
          "X-Mentor-Rcpt": rcpt,
          "X-Mentor-Timestamp": timestamp,
          "X-Mentor-Signature": signature,
        },
        body: raw,
        signal: AbortSignal.timeout(TIMEOUT_MS),
      });
    } catch (err) {
      console.error(JSON.stringify({ event: "gateway_unreachable", error: String(err && err.name), size: raw.length }));
      throw new Error("mentor gateway unreachable, try again later");
    }

    if (response.ok) {
      console.log(JSON.stringify({ event: "delivered", status: response.status, size: raw.length }));
      return;
    }
    console.error(JSON.stringify({ event: "gateway_error", status: response.status, size: raw.length }));
    if (response.status === 413) {
      message.setReject("Message too large for this mailbox (limit 25 MB including attachments)");
      return;
    }
    if (response.status === 400) {
      message.setReject("Recipient address not accepted");
      return;
    }
    // 429, 401/403/404 (secret or URL wrong), 5xx: temporary, the sending server should retry later
    throw new Error(`mentor gateway answered HTTP ${response.status}, try again later`);
  },
};
