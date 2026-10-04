import { useMemo, useState } from "react";
import {
  Store as StoreIcon,
  MapPinned,
  Package,
  Activity,
  Target,
  RotateCcw,
} from "lucide-react";
import StatCard from "../components/StatCard";
import OptimizationForm from "../components/OptimizationForm";
import OptimizationResults from "../components/OptimizationResults";
import ComparisonCard from "../components/ComparisonCard";
import MapView from "../components/MapView";
import DataSources from "../components/DataSources";
import PreviewModal from "../components/PreviewModal";
import {
  SelectedStores,
  AssignmentTable,
  InventoryTable,
} from "../components/Tables";
import { Button, Card, SectionTitle } from "../components/Primitives";
import ErrorState from "../components/ErrorState";
import EmptyState from "../components/EmptyState";
import LoadingState from "../components/LoadingState";
import {
  useDemand,
  useOptimizationRun,
  usePreview,
  useProducts,
  useStores,
} from "../hooks/useOptimization";
import { primaryResult, resultFor, solverLabel } from "../utils/formatters";

export default function Dashboard() {
  const stores = useStores();
  const products = useProducts();
  const demand = useDemand();
  const opt = useOptimizationRun();
  const preview = usePreview();
  const [previewOpen, setPreviewOpen] = useState(false);
  const [activeSolver, setActiveSolver] = useState("qaoa");

  const loading =
    stores.status === "loading" ||
    products.status === "loading" ||
    demand.status === "loading";

  const dataError = stores.error || products.error || demand.error;

  const candidateCount = useMemo(
    () => (stores.data || []).filter((s) => s.is_candidate).length,
    [stores.data],
  );

  const demandAreas = useMemo(
    () => Array.from(new Set((demand.data || []).map((d) => d.area))).sort(),
    [demand.data],
  );

  // Which solver's result is on screen. Defaults to QAOA when present.
  const shown = useMemo(() => {
    if (!opt.run) return null;
    return resultFor(opt.run, activeSolver) || primaryResult(opt.run);
  }, [opt.run, activeSolver]);

  const availableSolvers = useMemo(
    () => (opt.run?.results || []).map((r) => r.solver),
    [opt.run],
  );

  const openPreview = async (payload) => {
    setPreviewOpen(true);
    await preview.load(payload);
  };

  return (
    <div className="space-y-6">
      {/* ------------------------------------------------------- KPI row */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          icon={StoreIcon}
          label="Candidate Stores"
          value={candidateCount}
          hint={`${(stores.data || []).length} total in catalogue`}
          accent="brand"
          loading={stores.status === "loading"}
        />
        <StatCard
          icon={MapPinned}
          label="Demand Areas"
          value={demandAreas.length}
          hint={demandAreas.slice(0, 3).join(", ") || undefined}
          accent="violet"
          loading={demand.status === "loading"}
        />
        <StatCard
          icon={Package}
          label="Products"
          value={(products.data || []).length}
          hint={`${(demand.data || []).length} demand rows`}
          accent="emerald"
          loading={products.status === "loading"}
        />
        <StatCard
          icon={Activity}
          label="Optimization"
          value={
            opt.running
              ? "Running"
              : opt.run
                ? shown?.validation?.feasible
                  ? "Feasible"
                  : "Infeasible"
                : "Ready"
          }
          hint={opt.run ? `Run #${opt.run.id}` : "No run yet"}
          accent={opt.run ? (shown?.validation?.feasible ? "emerald" : "amber") : "ink"}
          badge={opt.run ? `method: ${opt.run.method}` : undefined}
          badgeTone={opt.run ? "info" : "neutral"}
        />
      </div>

      {dataError ? (
        <ErrorState
          error={dataError}
          onRetry={() => {
            stores.refresh();
            products.refresh();
            demand.refresh();
          }}
        />
      ) : null}

      {/* ------------------------------------------------ configuration */}
      {loading ? (
        <Card>
          <LoadingState label="Loading stores, products and demand..." rows={3} />
        </Card>
      ) : (
        <OptimizationForm
          stores={stores.data}
          products={products.data}
          demand={demand.data}
          running={opt.running}
          stage={opt.stage}
          onRun={opt.execute}
          onPreview={openPreview}
          previewLoading={preview.loading}
        />
      )}

      {opt.error ? <ErrorState error={opt.error} /> : null}

      {/* ------------------------------------------- data provenance */}
      <DataSources />

      {/* -------------------------------------------------------- map */}
      <MapView
        stores={stores.data}
        result={shown}
        demandAreas={demandAreas}
      />

      {/* ----------------------------------------------------- results */}
      {opt.running ? (
        <Card>
          <SectionTitle
            icon={Target}
            title="Optimization in progress"
            subtitle="Both solvers run on the same instance"
          />
          <div className="space-y-3">
            <LoadingState label={opt.stage} />
            <ol className="space-y-1.5 text-[12.5px]">
              {[
                "Preparing optimization model...",
                "Running QAOA...",
                "Running classical baseline...",
                "Validating solution...",
                "Saving results...",
              ].map((s, i) => (
                <li
                  key={s}
                  className={`flex items-center gap-2 ${
                    i <= opt.stageIndex ? "text-ink-700" : "text-ink-300"
                  }`}
                >
                  <span
                    className={`h-1.5 w-1.5 rounded-full ${
                      i < opt.stageIndex
                        ? "bg-emerald-500"
                        : i === opt.stageIndex
                          ? "animate-pulse bg-brand-500"
                          : "bg-ink-200"
                    }`}
                  />
                  {s}
                </li>
              ))}
            </ol>
            <p className="text-[11.5px] text-ink-400">
              Stage labels indicate the sequence the backend performs. The API
              exposes no progress stream, so no percentage is shown.
            </p>
          </div>
        </Card>
      ) : !opt.run ? (
        <Card>
          <EmptyState
            icon={Target}
            title="No optimization results yet."
            message="Configure your constraints and run the optimization to see recommended store locations, assignments and inventory allocation."
          />
        </Card>
      ) : (
        <>
          {/* solver switch */}
          {availableSolvers.length > 1 ? (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[12.5px] text-ink-500">Showing result:</span>
              {availableSolvers.map((s) => (
                <button
                  key={s}
                  onClick={() => setActiveSolver(s)}
                  className={`rounded-md border px-3 py-1.5 text-[12.5px] font-medium transition ${
                    (resultFor(opt.run, activeSolver) ? activeSolver : "qaoa") === s
                      ? "border-brand-300 bg-brand-50 text-brand-700"
                      : "border-ink-300 bg-white text-ink-600 hover:bg-ink-50"
                  }`}
                >
                  {solverLabel(s)}
                </button>
              ))}
              <Button
                variant="ghost"
                size="sm"
                icon={RotateCcw}
                onClick={opt.reset}
                className="ml-auto"
              >
                Clear results
              </Button>
            </div>
          ) : null}

          <OptimizationResults
            run={opt.run}
            result={shown}
            comparison={opt.comparison}
          />

          <div className="grid gap-6 xl:grid-cols-2">
            <SelectedStores result={shown} stores={stores.data} />
            <AssignmentTable result={shown} />
          </div>

          <InventoryTable result={shown} />

          <ComparisonCard comparison={opt.comparison} />
        </>
      )}

      <PreviewModal
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        data={preview.data}
        loading={preview.loading}
        error={preview.error}
      />
    </div>
  );
}
