import {
  CheckCircle2,
  XCircle,
  Target,
  Timer,
  Wallet,
  Boxes,
  Gauge,
  Store as StoreIcon,
  ShieldCheck,
} from "lucide-react";
import { Badge, Card, Metric, Note, SectionTitle, Table, Row } from "./Primitives";
import {
  money,
  moneyShort,
  num,
  pct,
  pctRaw,
  seconds,
  solverLabel,
  text,
} from "../utils/formatters";

/**
 * Result summary for one solver. Every value comes from the API payload; status
 * colouring is derived from the actual feasibility flag, never assumed.
 */
export default function OptimizationResults({ run, result, comparison }) {
  if (!result) return null;

  const v = result.validation || {};
  const feasible = v.feasible === true;
  const gapMap = comparison?.optimality_gap_percent || null;
  const gap = gapMap ? gapMap[result.solver] : null;
  const hasGap = typeof gap === "number";
  const referenceMatch = hasGap && Math.abs(gap) < 1e-6;

  return (
    <Card>
      <SectionTitle
        icon={Target}
        title={`${solverLabel(result.solver)} Result`}
        subtitle={
          run
            ? `Run #${run.id} · method "${text(run.method)}" · status ${text(run.status)}`
            : undefined
        }
        right={
          feasible ? (
            <Badge tone="success">
              <CheckCircle2 size={12} /> Feasible
            </Badge>
          ) : (
            <Badge tone="danger">
              <XCircle size={12} /> Infeasible
            </Badge>
          )
        }
      />

      <div className="grid gap-5 border-b border-ink-100 pb-5 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Objective Value"
          value={money(result.objective_value)}
          hint="served margin − opening − rider cost"
        />
        <Metric label="Runtime" value={seconds(result.runtime)} />
        <Metric
          label="Service Coverage"
          value={pct(result.service_level)}
          hint={`${num(result.demand_units_served)} / ${num(
            result.demand_units_total,
          )} demand units`}
          tone={result.service_level >= 0.999 ? "success" : "neutral"}
        />
        <Metric
          label="Optimality Gap"
          value={hasGap ? pctRaw(gap) : "Not available"}
          hint={
            hasGap
              ? `vs proven reference (${solverLabel(comparison.reference_solver)})`
              : "no proven reference on this run"
          }
          tone={referenceMatch ? "success" : "neutral"}
        />
      </div>

      <div className="grid gap-5 border-b border-ink-100 py-5 sm:grid-cols-2 lg:grid-cols-4">
        <Metric
          label="Budget Used"
          value={`${moneyShort(result.budget_used)} / ${moneyShort(
            result.budget_limit,
          )}`}
          hint={
            typeof result.budget_limit === "number" && result.budget_limit > 0
              ? `${((result.budget_used / result.budget_limit) * 100).toFixed(1)}% of budget`
              : undefined
          }
        />
        <Metric
          label="Storage Used"
          value={`${num(result.storage_used, 1)} / ${num(
            result.storage_available,
            1,
          )}`}
          hint={`${pct(result.storage_utilization)} of opened capacity`}
        />
        <Metric
          label="Stores Opened"
          value={num((result.selected_stores || []).length)}
          hint={(result.selected_store_names || []).join(", ") || undefined}
        />
        <Metric
          label="Demand Served"
          value={num(result.customers_served)}
          hint="demand units, not a headcount"
        />
      </div>

      {/* Reference-match statement, shown ONLY when the API reports a zero gap */}
      <div className="py-5">
        {hasGap ? (
          referenceMatch ? (
            <Note tone="info" icon={ShieldCheck}>
              <strong className="font-semibold">
                Matches classical reference optimum.
              </strong>{" "}
              The API reports a {pctRaw(gap)} gap against{" "}
              {solverLabel(comparison.reference_solver)}, which returned a proven
              optimum for this instance.
            </Note>
          ) : (
            <Note tone="warning">
              <strong className="font-semibold">
                {solverLabel(result.solver)} solution differs from the reference
                optimum
              </strong>{" "}
              by {pctRaw(gap)}. The plan is still validated independently;
              increasing circuit depth, shots or iterations may close the gap.
            </Note>
          )
        ) : (
          <Note tone="info">
            No optimality gap is reported: no solver on this run provided a
            proven optimum, so there is no valid reference to measure against.
          </Note>
        )}
      </div>

      {/* Independent validation detail */}
      <div className="border-t border-ink-100 pt-5">
        <div className="mb-3 flex items-center gap-2 text-[13px] font-semibold text-ink-800">
          <Gauge size={15} className="text-ink-400" />
          Independent constraint validation
        </div>
        {v.checks?.length ? (
          <Table
            head={[
              { label: "Constraint" },
              { label: "Status" },
              { label: "Used", align: "right" },
              { label: "Limit", align: "right" },
              { label: "Detail" },
            ]}
          >
            {v.checks.map((c) => (
              <Row key={c.name}>
                <td className="pr-3 font-medium text-ink-800">
                  {c.name.replace(/_/g, " ")}
                </td>
                <td className="pr-3">
                  {c.satisfied ? (
                    <Badge tone="success">Satisfied</Badge>
                  ) : (
                    <Badge tone="danger">Violated</Badge>
                  )}
                </td>
                <td className="tnum pr-3 text-right text-ink-600">
                  {typeof c.used === "number" ? num(c.used, 1) : "—"}
                </td>
                <td className="tnum pr-3 text-right text-ink-600">
                  {typeof c.limit === "number" ? num(c.limit, 1) : "—"}
                </td>
                <td className="text-[12px] text-ink-500">{text(c.detail)}</td>
              </Row>
            ))}
          </Table>
        ) : (
          <p className="text-[13px] text-ink-500">
            No validation checks were returned for this result.
          </p>
        )}

        {v.violations?.length ? (
          <div className="mt-4">
            <Note tone="danger">
              <strong className="font-semibold">
                {v.violations.length} constraint violation
                {v.violations.length === 1 ? "" : "s"} reported:
              </strong>
              <ul className="mt-1.5 list-disc space-y-1 pl-4">
                {v.violations.map((msg, i) => (
                  <li key={i}>{msg}</li>
                ))}
              </ul>
            </Note>
          </div>
        ) : null}
      </div>

      {/* Solver-specific detail, useful for a technical audience */}
      {result.solver_details ? (
        <div className="mt-5 border-t border-ink-100 pt-5">
          <div className="mb-3 text-[13px] font-semibold text-ink-800">
            Solver detail
          </div>
          <div className="grid gap-x-6 gap-y-2 text-[12.5px] sm:grid-cols-2 lg:grid-cols-3">
            {[
              ["Solver", result.solver_details.solver],
              ["Encoding", result.solver_details.encoding],
              ["Qubits", result.solver_details.n_qubits],
              ["Decision variables", result.solver_details.n_decision_variables],
              ["Auxiliary variables", result.solver_details.n_auxiliary_variables],
              ["Depth (p)", result.solver_details.reps_p],
              ["Shots", result.solver_details.final_shots],
              ["Circuit evaluations", result.solver_details.circuit_evaluations],
              ["PuLP status", result.solver_details.pulp_status],
              [
                "Proven optimal",
                typeof result.solver_details.proven_optimal === "boolean"
                  ? result.solver_details.proven_optimal
                    ? "Yes"
                    : "No"
                  : undefined,
              ],
              [
                "Feasible shot fraction",
                typeof result.solver_details.feasible_shot_fraction === "number"
                  ? pct(result.solver_details.feasible_shot_fraction, 2)
                  : undefined,
              ],
              ["Optimizer", result.solver_details.optimizer],
            ]
              .filter(([, val]) => val !== undefined && val !== null)
              .map(([label, val]) => (
                <div key={label} className="flex justify-between gap-3">
                  <span className="text-ink-400">{label}</span>
                  <span className="tnum text-right font-medium text-ink-700">
                    {String(val)}
                  </span>
                </div>
              ))}
          </div>

          {result.solver_details.notes?.length ? (
            <ul className="mt-4 space-y-1.5 text-[12px] leading-relaxed text-ink-500">
              {result.solver_details.notes.map((n, i) => (
                <li key={i} className="flex gap-2">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-ink-300" />
                  {n}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </Card>
  );
}

/** Compact KPI strip above the detailed result card. */
export function ResultKpis({ result }) {
  if (!result) return null;
  const feasible = result.validation?.feasible === true;
  const items = [
    {
      icon: feasible ? CheckCircle2 : XCircle,
      label: "Status",
      value: feasible ? "Feasible" : "Infeasible",
      accent: feasible ? "emerald" : "amber",
    },
    {
      icon: Target,
      label: "Objective",
      value: money(result.objective_value),
      accent: "brand",
    },
    { icon: Timer, label: "Runtime", value: seconds(result.runtime), accent: "violet" },
    {
      icon: Gauge,
      label: "Coverage",
      value: pct(result.service_level),
      accent: "emerald",
    },
    {
      icon: Wallet,
      label: "Budget",
      value: `${moneyShort(result.budget_used)} / ${moneyShort(result.budget_limit)}`,
      accent: "amber",
    },
    {
      icon: Boxes,
      label: "Storage",
      value: `${num(result.storage_used, 0)} / ${num(result.storage_available, 0)}`,
      accent: "ink",
    },
    {
      icon: StoreIcon,
      label: "Stores",
      value: num((result.selected_stores || []).length),
      accent: "brand",
    },
  ];
  return items;
}
