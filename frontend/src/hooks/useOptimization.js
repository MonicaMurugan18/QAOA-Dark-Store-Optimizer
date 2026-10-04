/**
 * Data hooks. All optimization state lives at the Dashboard level and is passed
 * down, so there is no global store and no Redux.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import {
  getComparison,
  getDemand,
  getHealth,
  getProducts,
  getRun,
  getRuns,
  getStores,
  previewOptimization,
  runOptimization,
  toFriendlyError,
} from "../services/api";

/** Generic fetch-once-with-refresh hook. */
export function useFetch(fn, deps = [], { immediate = true } = {}) {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState(immediate ? "loading" : "idle");
  const [error, setError] = useState(null);
  const alive = useRef(true);

  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
    };
  }, []);

  const load = useCallback(async () => {
    setStatus("loading");
    setError(null);
    try {
      const result = await fn();
      if (!alive.current) return result;
      setData(result);
      setStatus("ok");
      return result;
    } catch (err) {
      if (!alive.current) return null;
      setError(toFriendlyError(err));
      setStatus("error");
      return null;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    if (immediate) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [load, immediate]);

  return { data, status, error, refresh: load, setData };
}

/**
 * Polls GET /health so the header reflects reality rather than an assumption.
 * 20s is frequent enough to notice a restart without spamming the server.
 */
export function useHealth(intervalMs = 20000) {
  const h = useFetch(getHealth, []);
  useEffect(() => {
    const id = setInterval(() => h.refresh(), intervalMs);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [intervalMs]);
  return h;
}

export const useStores = () => useFetch(getStores, []);
export const useProducts = () => useFetch(getProducts, []);
export const useDemand = () => useFetch(getDemand, []);
export const useRuns = () => useFetch(getRuns, []);

/** Stages shown while a run is in flight. Labels only -- no fake percentage. */
export const RUN_STAGES = [
  "Preparing optimization model...",
  "Running QAOA...",
  "Running classical baseline...",
  "Validating solution...",
  "Saving results...",
];

/**
 * Drives an optimization run and holds its result + comparison.
 *
 * The stage label advances on a timer purely as a progress *indicator*. The
 * backend exposes no progress stream, so no percentage is invented and the
 * labels never claim a stage finished.
 */
export function useOptimizationRun() {
  const [running, setRunning] = useState(false);
  const [stageIndex, setStageIndex] = useState(0);
  const [run, setRun] = useState(null);
  const [comparison, setComparison] = useState(null);
  const [error, setError] = useState(null);
  const timer = useRef(null);

  const stopTicker = () => {
    if (timer.current) {
      clearInterval(timer.current);
      timer.current = null;
    }
  };

  useEffect(() => stopTicker, []);

  const execute = useCallback(async (payload) => {
    setRunning(true);
    setError(null);
    setStageIndex(0);
    stopTicker();

    // Advance the label, but stop before the last stage so the UI never claims
    // "Saving results" is done while the request is still open.
    timer.current = setInterval(() => {
      setStageIndex((i) => (i < RUN_STAGES.length - 1 ? i + 1 : i));
    }, 900);

    try {
      const result = await runOptimization(payload);
      setRun(result);

      // A comparison only exists when results were stored.
      if (result?.id && result?.results?.length) {
        try {
          setComparison(await getComparison(result.id));
        } catch {
          setComparison(null); // not fatal: the run itself succeeded
        }
      } else {
        setComparison(null);
      }
      return result;
    } catch (err) {
      setError(toFriendlyError(err));
      setRun(null);
      setComparison(null);
      return null;
    } finally {
      stopTicker();
      setRunning(false);
    }
  }, []);

  /** Load a historical run (and its comparison) into the dashboard. */
  const loadRun = useCallback(async (runId) => {
    setError(null);
    try {
      const result = await getRun(runId);
      setRun(result);
      try {
        setComparison(await getComparison(runId));
      } catch {
        setComparison(null);
      }
      return result;
    } catch (err) {
      setError(toFriendlyError(err));
      return null;
    }
  }, []);

  const reset = useCallback(() => {
    setRun(null);
    setComparison(null);
    setError(null);
  }, []);

  return {
    running,
    stage: RUN_STAGES[stageIndex],
    stageIndex,
    run,
    comparison,
    error,
    execute,
    loadRun,
    reset,
  };
}

/** QUBO preview, fetched on demand for the modal. */
export function usePreview() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async (payload) => {
    setLoading(true);
    setError(null);
    try {
      const result = await previewOptimization(payload);
      setData(result);
      return result;
    } catch (err) {
      setError(toFriendlyError(err));
      setData(null);
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  return { data, loading, error, load, clear: () => setData(null) };
}
