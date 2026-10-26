// Thin fetch helpers for the OdoAudit backend.

export async function api(url, opts = {}) {
  const init = { ...opts };
  if (opts.body && typeof opts.body !== "string" && !(opts.body instanceof FormData)) {
    init.body = JSON.stringify(opts.body);
    init.headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  }
  const res = await fetch(url, init);
  if (!res.ok) {
    let msg = `HTTP ${res.status}`;
    try {
      const j = await res.json();
      msg = typeof j.detail === "string" ? j.detail : msg;
    } catch {
      /* keep HTTP status */
    }
    throw new Error(msg);
  }
  return res.json();
}

export function uploadFile(file) {
  const fd = new FormData();
  fd.append("file", file);
  return api("/api/upload", { method: "POST", body: fd });
}
