/**
 * Single Axios client for the whole app.
 *
 * Every field name below was taken from the live backend schema at
 * /openapi.json, not guessed. The request shape for an optimization run is:
 *
 *   { budget, delivery_time_limit, store_ids, product_ids, areas,
 *     options: { reps, maxiter, shots, seed, time_limit_sec }, method }
 *
 * Note: the backend request schema has NO storage-capacity field. Storage is a
 * per-store property returned by /api/stores; it is not something a run can
 * override. The UI shows it as a derived read-only figure for that reason.
 */
import axios from "axios";

/**
 * THE one place the backend URL is defined.
 *
 * Set VITE_API_BASE_URL in frontend/.env. Vite inlines env vars at dev-server
 * START, so the server must be restarted after changing it -- editing .env
 * while `npm run dev` is running has no effect.
 *
 * No component may hardcode a URL or a port; they all import from here.
 */
export const API_BASE_URL = (
  import.meta.env.VITE_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 300000, // a deep QAOA run can take minutes; do not cut it off
  headers: { "Content-Type": "application/json" },
});

/**
 * Turn any Axios failure into a predictable, user-presentable shape.
 * Never surfaces a stack trace.
 */
export function toFriendlyError(error) {
  // --- no response at all: network / CORS / server down ---
  if (!error.response) {
    if (error.code === "ECONNABORTED") {
      return {
        status: 0,
        title: "Request timed out",
        message:
          "The backend did not respond in time. A very deep QAOA run can take " +
          "a while — try fewer iterations or a lower circuit depth.",
        fields: [],
      };
    }
    return {
      status: 0,
      title: "Cannot reach the backend",
      message:
        `Backend unreachable at ${API_BASE_URL}. ` +
        "Check that the FastAPI server is running and that VITE_API_BASE_URL " +
        "points at it.",
      fields: [],
    };
  }

  const { status, data } = error.response;

  // --- FastAPI validation errors from our custom handler ---
  // Shape: { error, path, problems: [{ field, message, type }], hint }
  if (status === 422 && Array.isArray(data?.problems)) {
    return {
      status,
      title: "Invalid input",
      message: data.hint || "Please correct the highlighted values.",
      fields: data.problems.map((p) => ({
        field: p.field?.replace(/^body\./, "") || "",
        message: p.message || "",
      })),
    };
  }

  // --- plain FastAPI 422 (Pydantic default shape) ---
  if (status === 422 && Array.isArray(data?.detail)) {
    return {
      status,
      title: "Invalid input",
      message: "Please correct the highlighted values.",
      fields: data.detail.map((d) => ({
        field: (d.loc || []).filter((x) => x !== "body").join("."),
        message: d.msg || "",
      })),
    };
  }

  // --- detail may be a string or an object, depending on the endpoint ---
  const detail = data?.detail;
  let message = "";
  if (typeof detail === "string") message = detail;
  else if (detail && typeof detail === "object")
    message = detail.message || detail.error || JSON.stringify(detail);
  else message = data?.detail || data?.error || data?.message || "";

  const titles = {
    400: "Bad request",
    404: "Not found",
    409: "Conflict",
    422: "Invalid input",
    500: "Optimization failed",
    503: "Service unavailable",
  };

  return {
    status,
    title: titles[status] || `Request failed (${status})`,
    message:
      message ||
      "The backend rejected the request but did not explain why. Check the server log.",
    fields: [],
  };
}

// ----------------------------------------------------------------- reads
export const getHealth = () => api.get("/health").then((r) => r.data);
export const getStores = () => api.get("/api/stores").then((r) => r.data);
export const getStore = (id) => api.get(`/api/stores/${id}`).then((r) => r.data);
export const getProducts = () => api.get("/api/products").then((r) => r.data);
export const getProduct = (id) =>
  api.get(`/api/products/${id}`).then((r) => r.data);
export const getDemand = () => api.get("/api/demand").then((r) => r.data);

// --------------------------------------------------------- optimization
export const previewOptimization = (payload) =>
  api.post("/api/optimization/preview", payload).then((r) => r.data);

export const runOptimization = (payload) =>
  api.post("/api/optimization/run", payload).then((r) => r.data);

export const runQaoa = (payload) =>
  api.post("/api/optimization/qaoa", payload).then((r) => r.data);

export const runClassical = (payload) =>
  api.post("/api/optimization/classical", payload).then((r) => r.data);

export const getSuggestedInstance = (params = {}) =>
  api
    .get("/api/optimization/suggest-instance", { params })
    .then((r) => r.data);

export const getRuns = () =>
  api.get("/api/optimization/runs").then((r) => r.data);

export const getRun = (runId) =>
  api.get(`/api/optimization/${runId}`).then((r) => r.data);

export const getComparison = (runId) =>
  api.get(`/api/optimization/${runId}/comparison`).then((r) => r.data);

export default api;
