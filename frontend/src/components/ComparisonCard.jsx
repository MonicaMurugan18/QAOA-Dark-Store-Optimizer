import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RTooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";
import { GitCompare, CheckCircle2, XCircle } from "lucide-react";
import { Badge, Card, Note, Row, SectionTitle, Table } from "./Primitives";
import {
  money,
  moneyShort,
  num,
  pct,
  pctRaw,
  seconds,
  solverLabel,
} from "../utils/formatters";

const QAOA_COLOR = "#3465f0";
const CLASSICAL_COLOR = "#0d9488";

/**
 * QAOA vs classical comparison.
 *
 * Deliberately avoids ranking language. No "better", "faster" or "superior"
 * claim is made anywhere -- only the measured values the API returned. The
 * `better` field the backend computes per metric is shown as a neutral
 * "lower"/"higher" note rather than a verdict on the algorithms.
 */
export default function ComparisonCard({ comparison }) {
  if (!comparison) return null;

  const q = comparison.qaoa;
  const c = comparison.classical;
  const bothPresent = Boolean(q && c);
  const gaps = comparison.optimality_gap_percent || null;

  const runtimeData = [];
  if (q) runtimeData.push({ name: "QAOA", value: q.runtime, fill: QAOA_COLOR });
  if (c)
    runtimeData.push({
      name: "Classical",
      value: c.runtime,
      fill: CLASSICAL_COLOR,
    });

  const objectiveData = [];
  if (q)
    objectiveData.push({
      name: "QAOA",
      value: q.objective_value,
      fill: QAOA_COLOR,
    });
  if (c)
    objectiveData.push({
      name: "Classical",
      value: c.objective_value,
      fill: CLASSICAL_COLOR,
    });

  const rows = [
    {
      label: "Objective value",
      q: money(q?.objective_value),
      c: money(c?.objective_value),
    },
    { label: "Runtime", q: seconds(q?.runtime), c: seconds(c?.runtime) },
    {
      label: "Demand served",
      q: num(q?.customers_served),
      c: num(c?.customers_served),
    },
    { label: "Coverage", q: pct(q?.service_level), c: pct(c?.service_level) },
    {
      label: "Budget used",
      q: moneyShort(q?.budget_used),
      c: moneyShort(c?.budget_used),
    },
    {
      label: "Storage utilization",
      q: pct(q?.storage_utilization),
      c: pct(c?.storage_utilization),
    },
    {
      label: "Stores opened",
      q: q ? num(q.selected_stores?.length) : "—",
      c: c ? num(c.selected_stores?.length) : "—",
    },
    {
      label: "Optimality gap",
      q: gaps && typeof gaps.qaoa === "number" ? pctRaw(gaps.qaoa) : "Not available",
      c:
        gaps && typeof gaps.classical === "number"
          ? pctRaw(gaps.classical)
          : "Not available",
    },
  ];

  const feasibilityCell = (block) => {
    if (!block) return <span className="text-ink-400">—</span>;
    return block.feasible ? (
      <Badge tone="success">
        <CheckCircle2 size={12} /> Yes
      </Badge>
    ) : (
      <Badge tone="danger">
        <XCircle size={12} /> No
      </Badge>
    );
  };

  return (
    <Card>
      <SectionTitle
        icon={GitCompare}
        title="QAOA vs Classical Baseline"
        subtitle="Same instance, same constraints, two solvers. Measured values only."
        right={
          comparison.reference_solver ? (
            <Badge tone="info">
              Reference: {solverLabel(comparison.reference_solver)}
            </Badge>
          ) : (
            <Badge tone="neutral">No proven reference</Badge>
          )
        }
      />

      {!bothPresent ? (
        <div className="mb-4">
          <Note tone="warning">
            Only {q ? "the QAOA" : c ? "the classical" : "no"} result is stored
            for this run, so a side-by-side comparison is incomplete. Run with
            method <code className="font-mono text-[11px]">both</code> to compare.
          </Note>
        </div>
      ) : null}

      <Table
        head={[
          { label: "Metric" },
          { label: "QAOA", align: "right" },
          { label: "Classical", align: "right" },
        ]}
      >
        <Row>
          <td className="pr-3 font-medium text-ink-800">Feasible</td>
          <td className="pr-3 text-right">{feasibilityCell(q)}</td>
          <td className="text-right">{feasibilityCell(c)}</td>
        </Row>
        {rows.map((r) => (
          <Row key={r.label}>
            <td className="pr-3 font-medium text-ink-800">{r.label}</td>
            <td className="tnum pr-3 text-right text-ink-700">{r.q}</td>
            <td className="tnum text-right text-ink-700">{r.c}</td>
          </Row>
        ))}
        <Row>
          <td className="pr-3 font-medium text-ink-800">Constraint violations</td>
          <td className="tnum pr-3 text-right text-ink-700">
            {q ? num(q.constraint_violations?.length ?? 0) : "—"}
          </td>
          <td className="tnum text-right text-ink-700">
            {c ? num(c.constraint_violations?.length ?? 0) : "—"}
          </td>
        </Row>
      </Table>

      {/* Charts */}
      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <div>
          <div className="mb-2 text-[12.5px] font-semibold text-ink-700">
            Runtime (seconds)
          </div>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={runtimeData}
                margin={{ top: 4, right: 8, bottom: 4, left: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#eef0f4" vertical={false} />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 12, fill: "#5f6b82" }}
                  axisLine={{ stroke: "#dde1e9" }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: "#8d97ab" }}
                  axisLine={false}
                  tickLine={false}
                  width={56}
                />
                <RTooltip
                  formatter={(v) => [seconds(v), "Runtime"]}
                  contentStyle={{
                    fontSize: 12,
                    borderRadius: 8,
                    border: "1px solid #dde1e9",
                  }}
                />
                <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={72}>
                  {runtimeData.map((d) => (
                    <Cell key={d.name} fill={d.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-1 text-[11.5px] text-ink-400">
            Measured wall-clock time. QAOA runs on a statevector simulator, not
            quantum hardware.
          </p>
        </div>

        <div>
          <div className="mb-2 text-[12.5px] font-semibold text-ink-700">
            Objective value (INR)
          </div>
          <div className="h-48">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={objectiveData}
                margin={{ top: 4, right: 8, bottom: 4, left: 0 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke="#eef0f4" vertical={false} />
                <XAxis
                  dataKey="name"
                  tick={{ fontSize: 12, fill: "#5f6b82" }}
                  axisLine={{ stroke: "#dde1e9" }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: "#8d97ab" }}
                  axisLine={false}
                  tickLine={false}
                  width={64}
                  tickFormatter={(v) => `${(v / 1000).toFixed(0)}k`}
                />
                <RTooltip
                  formatter={(v) => [money(v), "Objective"]}
                  contentStyle={{
                    fontSize: 12,
                    borderRadius: 8,
                    border: "1px solid #dde1e9",
                  }}
                />
                <Bar dataKey="value" radius={[4, 4, 0, 0]} maxBarSize={72}>
                  {objectiveData.map((d) => (
                    <Cell key={d.name} fill={d.fill} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
          <p className="mt-1 text-[11.5px] text-ink-400">
            Higher is better for this objective: served margin minus opening and
            rider cost.
          </p>
        </div>
      </div>

      {comparison.notes?.length ? (
        <ul className="mt-6 space-y-1.5 border-t border-ink-100 pt-4 text-[12px] leading-relaxed text-ink-500">
          {comparison.notes.map((n, i) => (
            <li key={i} className="flex gap-2">
              <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-ink-300" />
              {n}
            </li>
          ))}
        </ul>
      ) : null}
    </Card>
  );
}
