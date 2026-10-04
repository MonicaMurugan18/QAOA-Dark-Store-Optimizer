/**
 * Display helpers.
 *
 * Every function tolerates null/undefined and returns an explicit placeholder
 * rather than inventing a value. If the API does not provide a field, the UI
 * shows a dash -- it never shows a made-up number.
 */

export const DASH = "—"; // em dash, used for "not provided"

export function isNum(v) {
  return typeof v === "number" && Number.isFinite(v);
}

/** Indian-format currency, e.g. 14716.1402 -> "₹14,716.14" */
export function money(v, decimals = 2) {
  if (!isNum(v)) return DASH;
  return `₹${v.toLocaleString("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })}`;
}

/** Currency with no paise, for budgets: "₹20,000" */
export function moneyShort(v) {
  if (!isNum(v)) return DASH;
  return `₹${Math.round(v).toLocaleString("en-IN")}`;
}

export function num(v, decimals = 0) {
  if (!isNum(v)) return DASH;
  return v.toLocaleString("en-IN", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** Fraction (0..1) as a percentage: 0.716912 -> "71.7%" */
export function pct(v, decimals = 1) {
  if (!isNum(v)) return DASH;
  return `${(v * 100).toFixed(decimals)}%`;
}

/** Already-a-percentage value: 0.0 -> "0.00%", -3.4 -> "-3.40%" */
export function pctRaw(v, decimals = 2) {
  if (!isNum(v)) return DASH;
  return `${v.toFixed(decimals)}%`;
}

/** Seconds, scaled so sub-second runtimes stay readable. */
export function seconds(v) {
  if (!isNum(v)) return DASH;
  if (v < 0.001) return "<1 ms";
  if (v < 1) return `${(v * 1000).toFixed(0)} ms`;
  return `${v.toFixed(3)} s`;
}

export function minutes(v) {
  if (!isNum(v)) return DASH;
  return `${v.toFixed(1)} min`;
}

export function dateTime(iso) {
  if (!iso) return DASH;
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return DASH;
  return d.toLocaleString("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function text(v) {
  if (v === null || v === undefined || v === "") return DASH;
  return String(v);
}

/** Title-case a solver key: "qaoa" -> "QAOA", "classical" -> "Classical" */
export function solverLabel(key) {
  if (!key) return DASH;
  if (key.toLowerCase() === "qaoa") return "QAOA";
  return key.charAt(0).toUpperCase() + key.slice(1);
}

/**
 * Approximate the centre of a demand area from the candidate stores that share
 * its name.
 *
 * IMPORTANT: this is NOT invented geography. The backend itself locates each
 * area at the centroid of the stores sharing that area name (documented in
 * app/services/data_service.py), and the /api/demand endpoint returns no
 * coordinates at all. We reuse the backend's own derivation so the map agrees
 * with the delivery times the solver actually used, and the UI labels every
 * such marker as approximate.
 *
 * Returns null when no store shares the area name, in which case the caller
 * must omit the marker rather than guess.
 */
export function areaCentroidFromStores(areaName, stores) {
  const matches = (stores || []).filter(
    (s) => s.area === areaName && isNum(s.latitude) && isNum(s.longitude),
  );
  if (matches.length === 0) return null;
  const lat = matches.reduce((a, s) => a + s.latitude, 0) / matches.length;
  const lng = matches.reduce((a, s) => a + s.longitude, 0) / matches.length;
  return { lat, lng, derivedFrom: matches.length };
}

/** Pick the result block for a solver key out of a run payload. */
export function resultFor(run, solver) {
  if (!run?.results) return null;
  return run.results.find((r) => r.solver === solver) || null;
}

/** The result to feature in the UI: QAOA if present, else whatever exists. */
export function primaryResult(run) {
  if (!run?.results?.length) return null;
  return resultFor(run, "qaoa") || run.results[0];
}
