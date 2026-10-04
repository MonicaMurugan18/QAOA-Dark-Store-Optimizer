import { useEffect, useMemo, useState } from "react";
import { Play, Eye, Settings2, Sliders, Loader2 } from "lucide-react";
import {
  Button,
  Card,
  Field,
  Note,
  NumberInput,
  SectionTitle,
} from "./Primitives";
import { moneyShort, num } from "../utils/formatters";
import { getSuggestedInstance } from "../services/api";

/**
 * Builds the exact request body the backend expects:
 *
 *   { budget, delivery_time_limit, store_ids, product_ids, areas,
 *     options: { reps, maxiter, shots, seed, time_limit_sec }, method: "both" }
 *
 * Field names come from /openapi.json. There is deliberately NO storage-capacity
 * input: the request schema has no such field. Storage is a per-store property
 * from /api/stores, so it is shown read-only instead of pretending it is a knob.
 */
export default function OptimizationForm({
  stores,
  products,
  demand,
  running,
  stage,
  onRun,
  onPreview,
  previewLoading,
}) {
  const [budget, setBudget] = useState("20000");
  const [deliveryLimit, setDeliveryLimit] = useState("15");
  const [reps, setReps] = useState("3");
  const [maxiter, setMaxiter] = useState("150");
  const [shots, setShots] = useState("2048");
  const [seed, setSeed] = useState("42");
  const [timeLimit, setTimeLimit] = useState("30");
  const [scope, setScope] = useState("dev"); // dev = 3x3x3, all = everything
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [errors, setErrors] = useState({});

  const candidates = useMemo(
    () => (stores || []).filter((s) => s.is_candidate),
    [stores],
  );

  const demandAreas = useMemo(
    () => Array.from(new Set((demand || []).map((d) => d.area))).sort(),
    [demand],
  );

  /**
   * The solver-sized instance is chosen BY THE BACKEND, not here.
   *
   * It queries which demand zones actually have demand and are reachable by a
   * routed leg inside the delivery promise, then picks the stores that serve
   * them. Matching stores to areas by name in the browser used to work when
   * both came from one seed file; with real OSM data a store's `area` tag and a
   * demand zone's name are independent, so that approach silently produced an
   * empty instance.
   */
  const [devScope, setDevScope] = useState({
    store_ids: [],
    product_ids: [],
    areas: [],
    rationale: null,
  });
  const [scopeError, setScopeError] = useState(null);

  useEffect(() => {
    let alive = true;
    getSuggestedInstance({ delivery_time_limit: Number(deliveryLimit) || 15 })
      .then((d) => {
        if (alive) {
          setDevScope(d);
          setScopeError(null);
        }
      })
      .catch(() => {
        if (alive)
          setScopeError(
            "Could not propose an instance from the current data. Run the " +
              "ingestion pipeline, or widen the delivery limit.",
          );
      });
    return () => {
      alive = false;
    };
  }, [deliveryLimit]);

  const totalStorage = useMemo(
    () =>
      (scope === "dev"
        ? candidates.filter((s) => devScope.store_ids.includes(s.id))
        : candidates
      ).reduce((a, s) => a + (s.storage_capacity || 0), 0),
    [candidates, devScope, scope],
  );

  function validate() {
    const e = {};
    const b = Number(budget);
    const d = Number(deliveryLimit);
    const r = Number(reps);
    const m = Number(maxiter);
    const sh = Number(shots);

    if (!Number.isFinite(b) || b < 0) e.budget = "Budget must be 0 or more.";
    const cheapest = Math.min(
      ...(candidates.length ? candidates.map((s) => s.opening_cost) : [0]),
    );
    if (Number.isFinite(b) && candidates.length && b < cheapest)
      e.budget = `Below the cheapest store (${moneyShort(cheapest)}); no store could be opened.`;
    if (!Number.isFinite(d) || d <= 0)
      e.deliveryLimit = "Delivery limit must be greater than 0.";
    if (!Number.isFinite(r) || r < 1 || r > 12) e.reps = "Depth must be 1-12.";
    if (!Number.isFinite(m) || m < 1 || m > 5000)
      e.maxiter = "Iterations must be 1-5000.";
    if (!Number.isFinite(sh) || sh < 32 || sh > 100000)
      e.shots = "Shots must be 32-100000.";

    setErrors(e);
    return Object.keys(e).length === 0;
  }

  function buildPayload() {
    const base = {
      budget: Number(budget),
      delivery_time_limit: Number(deliveryLimit),
      options: {
        reps: Number(reps),
        maxiter: Number(maxiter),
        shots: Number(shots),
        seed: Number(seed),
        time_limit_sec: Number(timeLimit),
      },
    };
    if (scope === "dev") {
      base.store_ids = devScope.store_ids;
      base.product_ids = devScope.product_ids;
      base.areas = devScope.areas;
    }
    return base;
  }

  const submit = (e) => {
    e.preventDefault();
    if (!validate()) return;
    onRun({ ...buildPayload(), method: "both" });
  };

  const preview = () => {
    if (!validate()) return;
    onPreview(buildPayload());
  };

  const scopeStores = scope === "dev" ? devScope.store_ids.length : candidates.length;
  const scopeAreas = scope === "dev" ? devScope.areas.length : demandAreas.length;
  const scopeProducts =
    scope === "dev" ? devScope.product_ids.length : (products || []).length;

  return (
    <Card>
      <SectionTitle
        icon={Settings2}
        title="Optimization Configuration"
        subtitle="Constraints and solver settings. Both solvers receive the identical instance."
        right={
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="inline-flex items-center gap-1.5 text-[12.5px] font-medium text-brand-600 hover:text-brand-700"
          >
            <Sliders size={14} />
            {showAdvanced ? "Hide" : "Show"} QAOA parameters
          </button>
        }
      />

      <form onSubmit={submit} className="space-y-5">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <Field
            label="Budget"
            hint="Total opening-cost spend allowed"
            error={errors.budget}
          >
            <NumberInput
              value={budget}
              onChange={setBudget}
              min={0}
              step={500}
              suffix="INR"
              error={errors.budget}
              disabled={running}
            />
          </Field>

          <Field
            label="Delivery Limit"
            hint="Fallback service promise; an area's own limit wins"
            error={errors.deliveryLimit}
          >
            <NumberInput
              value={deliveryLimit}
              onChange={setDeliveryLimit}
              min={1}
              step={1}
              suffix="min"
              error={errors.deliveryLimit}
              disabled={running}
            />
          </Field>

          <Field
            label="Storage Capacity"
            hint="Sum of the selected candidates' capacity — a store property, not a run input"
          >
            <div className="tnum flex items-center rounded-md border border-ink-200 bg-ink-50 px-3 py-2 text-[13.5px] text-ink-600">
              {num(totalStorage)}
              <span className="ml-auto text-[12px] text-ink-400">units</span>
            </div>
          </Field>
        </div>

        <Field
          label="Instance scope"
          hint="The simulator holds 2^n amplitudes, so the full catalogue may exceed the qubit limit."
        >
          <div className="flex flex-wrap gap-2">
            {[
              { key: "dev", label: "Solver-sized instance (auto-selected)" },
              { key: "all", label: "All candidate stores and areas" },
            ].map((opt) => (
              <button
                key={opt.key}
                type="button"
                disabled={running}
                onClick={() => setScope(opt.key)}
                className={`rounded-md border px-3 py-1.5 text-[12.5px] font-medium transition disabled:opacity-60 ${
                  scope === opt.key
                    ? "border-brand-300 bg-brand-50 text-brand-700"
                    : "border-ink-300 bg-white text-ink-600 hover:bg-ink-50"
                }`}
              >
                {opt.label}
              </button>
            ))}
            <span className="self-center text-[12px] text-ink-400">
              {scopeStores} stores · {scopeAreas} areas · {scopeProducts} products
            </span>
            {scope === "dev" && devScope.rationale ? (
              <span className="w-full text-[11.5px] text-ink-400">
                {devScope.rationale}
              </span>
            ) : null}
            {scopeError ? (
              <span className="w-full text-[11.5px] text-red-600">
                {scopeError}
              </span>
            ) : null}
          </div>
        </Field>

        {showAdvanced ? (
          <div className="rounded-md border border-ink-200 bg-ink-50/60 p-4">
            <div className="mb-3 text-[12.5px] font-semibold text-ink-700">
              QAOA parameters
            </div>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
              <Field label="Depth (reps / p)" error={errors.reps}>
                <NumberInput
                  value={reps}
                  onChange={setReps}
                  min={1}
                  max={12}
                  error={errors.reps}
                  disabled={running}
                />
              </Field>
              <Field label="Max iterations" error={errors.maxiter}>
                <NumberInput
                  value={maxiter}
                  onChange={setMaxiter}
                  min={1}
                  max={5000}
                  error={errors.maxiter}
                  disabled={running}
                />
              </Field>
              <Field label="Shots" error={errors.shots}>
                <NumberInput
                  value={shots}
                  onChange={setShots}
                  min={32}
                  max={100000}
                  error={errors.shots}
                  disabled={running}
                />
              </Field>
              <Field label="Seed">
                <NumberInput
                  value={seed}
                  onChange={setSeed}
                  min={0}
                  disabled={running}
                />
              </Field>
              <Field label="CBC time limit" hint="classical solver">
                <NumberInput
                  value={timeLimit}
                  onChange={setTimeLimit}
                  min={1}
                  max={3600}
                  suffix="s"
                  disabled={running}
                />
              </Field>
            </div>
            <div className="mt-3">
              <Note tone="info">
                Circuit depth drives solution quality. Low depth finishes in
                milliseconds but typically returns a feasible yet suboptimal
                plan, and the result panel reports that rather than hiding it.
              </Note>
            </div>
          </div>
        ) : null}

        <div className="flex flex-wrap items-center gap-3 border-t border-ink-100 pt-4">
          <Button type="submit" disabled={running} icon={running ? null : Play}>
            {running ? (
              <>
                <Loader2 size={15} className="animate-spin" />
                Running…
              </>
            ) : (
              "Run Optimization"
            )}
          </Button>
          <Button
            type="button"
            variant="secondary"
            icon={previewLoading ? null : Eye}
            onClick={preview}
            disabled={running || previewLoading}
          >
            {previewLoading ? (
              <>
                <Loader2 size={15} className="animate-spin" />
                Loading…
              </>
            ) : (
              "Preview QUBO"
            )}
          </Button>

          {running ? (
            <span className="inline-flex items-center gap-2 text-[12.5px] text-ink-600">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-brand-500" />
              {stage}
            </span>
          ) : (
            <span className="text-[12px] text-ink-400">
              Runs QAOA and the classical baseline on the same instance
            </span>
          )}
        </div>
      </form>
    </Card>
  );
}
