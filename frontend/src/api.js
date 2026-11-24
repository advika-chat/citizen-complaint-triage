const API_BASE = import.meta.env.VITE_API_BASE || "http://localhost:8000";

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`${API_BASE}${path}`, options);
  } catch {
    throw new Error("Cannot reach the server. Is the backend running?");
  }
  if (!res.ok) {
    if (res.status === 429) {
      throw new Error("You are submitting too quickly. Please wait a minute and try again.");
    }
    let detail = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail) && body.detail[0]?.msg) detail = body.detail[0].msg;
    } catch {
      /* keep default message */
    }
    throw new Error(detail);
  }
  return res.json();
}

const json = (method, body) => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export function createComplaint({ text, latitude, longitude, photo }) {
  const form = new FormData();
  form.append("text", text);
  if (latitude != null) form.append("latitude", latitude);
  if (longitude != null) form.append("longitude", longitude);
  if (photo) form.append("photo", photo);
  return request("/complaints", { method: "POST", body: form });
}

export function getComplaints(filters = {}) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v !== "" && v != null) params.append(k, v);
  });
  return request(`/complaints?${params}`);
}

export const searchComplaints = (q, limit = 10) =>
  request(`/complaints/search?${new URLSearchParams({ q, limit })}`);
export const getComplaint = (id) => request(`/complaints/${id}`);
export const updateComplaintStatus = (id, status) => request(`/complaints/${id}`, json("PATCH", { status }));
export const bulkUpdateStatus = (ids, status) => request("/complaints/bulk-status", json("PATCH", { ids, status }));
export const addNote = (id, text) => request(`/complaints/${id}/notes`, json("POST", { text }));
export const getAnalyticsSummary = () => request("/analytics/summary");
export const getLlmAnalytics = () => request("/analytics/llm");
export const getHealth = () => request("/health");
export const photoUrl = (path) => (path ? `${API_BASE}${path}` : null);
