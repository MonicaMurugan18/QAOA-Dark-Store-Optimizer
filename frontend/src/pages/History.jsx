import { useState } from "react";
import { History as HistoryIcon, ChevronRight, RefreshCw } from "lucide-react";
import {
  Badge,
  Button,
  Card,
  Row,
  SectionTitle,
  Table,
} from "../components/Primitives";
import LoadingState from "../components/LoadingState";
import ErrorState from "../components/ErrorState";
import EmptyState from "../components/EmptyState";
import OptimizationResults from "../components/OptimizationResults";
import ComparisonCard from "../components/ComparisonCard";
import {
  SelectedStores,
  AssignmentTable,
  InventoryTable,
} from "../components/Tables";
import { useOptimizationRun, useRuns, useStores } from "../hooks/useOptimization";
import {
  dateTime,
  money,
  moneyShort,
  resultFor,
  seconds,
  solverLabel,
  text,
} from "../utils/formatters";

export default function History() {
  const runs = useRuns();
  const stores = useStores();
  const detail = useOptimizationRun();
  const [loadingId, setLoadingId] = useState(null);
  const [activeSolver, setActiveSolver] = useState("qaoa");

  const open = async (runId) => {
    setLoadingId(runId);
    await detail.loadRun(runId);
    setLoadingId(null);
  };

  const shown = detail.run
    ? resultFor(detail.run, activeSolver) || detail.run.results?.[0]
    : null;
  const availableSolvers = (detail.run?.results || []).map((r) => r.solver);

  return (
    <div className="space-y-6">
      <Card>
        <SectionTitle
          icon={HistoryIcon}
          title="Optimization History"
          subtitle="Runs persisted by the backend. Click a row to load its results."
          right={
            <Button
              variant="secondary"
              size="sm"
              icon={RefreshCw}
              onClick={runs.refresh}
            >
              Refresh
            </Button>
          }
        />

        {runs.status === "loading" ? (
          <LoadingState label="Loading previous runs..." rows={4} />
        ) : runs.status === "error" ? (
          <ErrorState error={runs.error} onRetry={runs.refresh} />
        ) : !(runs.data || []).length ? (
          <EmptyState
            icon={HistoryIcon}
            title="No optimization runs yet"
            message="Run an optimization from the dashboard and it will appear here."
          />
        ) : (
          <Table
            head={[
              { label: "Run ID" },
              { label: "Date / Time" },
              { label: "Method" },
              { label: "Budget", align: "right" },
              { label: "Delivery limit", align: "right" },
              { label: "Status" },
              { label: "" },
            ]}
          >
            {runs.data.map((r) => (
              <Row
                key={r.id}
                onClick={() => open(r.id)}
                active={detail.run?.id === r.id}
              >
                <td className="tnum pr-3 font-medium text-ink-800">#{r.id}</td>
                <td className="pr-3 text-[12.5px] text-ink-600">
                  {dateTime(r.created_at)}
                </td>
                <td className="pr-3">
                  <Badge tone={r.method === "both" ? "info" : "neutral"}>
                    {text(r.method)}
                  </Badge>
                </td>
                <td className="tnum pr-3 text-right text-ink-600">
                  {moneyShort(r.budget)}
                </td>
                <td className="tnum pr-3 text-right text-ink-600">
                  {r.delivery_time_limit} min
                </td>
                <td className="pr-3">
                  {r.status === "completed" ? (
                    <Badge tone="success">completed</Badge>
                  ) : r.status === "failed" ? (
                    <Badge tone="danger">failed</Badge>
                  ) : (
                    <Badge tone="warning">{text(r.status)}</Badge>
                  )}
                </td>
                <td className="text-right text-ink-400">
                  {loadingId === r.id ? (
                    <span className="text-[11.5px]">loading…</span>
                  ) : (
                    <ChevronRight size={16} />
                  )}
                </td>
              </Row>
            ))}
          </Table>
        )}

        <p className="mt-3 text-[11.5px] text-ink-400">
          Objective and runtime are stored per solver, so they appear once a run
          is opened below rather than in this list.
        </p>
      </Card>

      {detail.error ? <ErrorState error={detail.error} /> : null}

      {detail.run ? (
        <>
          <Card>
            <SectionTitle
              icon={HistoryIcon}
              title={`Run #${detail.run.id}`}
              subtitle={`${dateTime(detail.run.created_at)} · method "${text(
                detail.run.method,
              )}" · ${text(detail.run.status)}`}
              right={
                availableSolvers.length > 1 ? (
                  <div className="flex gap-2">
                    {availableSolvers.map((s) => (
                      <button
                        key={s}
                        onClick={() => setActiveSolver(s)}
                        className={`rounded-md border px-2.5 py-1 text-[12px] font-medium ${
                          (resultFor(detail.run, activeSolver)
                            ? activeSolver
                            : availableSolvers[0]) === s
                            ? "border-brand-300 bg-brand-50 text-brand-700"
                            : "border-ink-300 bg-white text-ink-600 hover:bg-ink-50"
                        }`}
                      >
                        {solverLabel(s)}
                      </button>
                    ))}
                  </div>
                ) : null
              }
            />
            {detail.run.error_message ? (
              <div className="mb-4 rounded-md border border-amber-200 bg-amber-50 p-3 text-[12.5px] text-amber-900">
                <strong className="font-semibold">Solver errors:</strong>{" "}
                {detail.run.error_message}
              </div>
            ) : null}
            <div className="grid gap-x-6 gap-y-2 text-[12.5px] sm:grid-cols-2 lg:grid-cols-4">
              {(detail.run.results || []).map((r) => (
                <div
                  key={r.solver}
                  className="rounded-md border border-ink-200 p-3"
                >
                  <div className="text-[11px] font-medium uppercase tracking-wide text-ink-400">
                    {solverLabel(r.solver)}
                  </div>
                  <div className="tnum mt-1 text-[16px] font-semibold text-ink-900">
                    {money(r.objective_value)}
                  </div>
                  <div className="tnum mt-0.5 text-[11.5px] text-ink-400">
                    {seconds(r.runtime)}
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {shown ? (
            <>
              <OptimizationResults
                run={detail.run}
                result={shown}
                comparison={detail.comparison}
              />
              <div className="grid gap-6 xl:grid-cols-2">
                <SelectedStores result={shown} stores={stores.data} />
                <AssignmentTable result={shown} />
              </div>
              <InventoryTable result={shown} />
            </>
          ) : (
            <Card>
              <EmptyState
                icon={HistoryIcon}
                title="This run stored no results"
                message={
                  detail.run.error_message ||
                  "Every requested solver failed, so there is nothing to display."
                }
              />
            </Card>
          )}

          <ComparisonCard comparison={detail.comparison} />
        </>
      ) : null}
    </div>
  );
}
