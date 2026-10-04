import {
  Store as StoreIcon,
  MapPin,
  Boxes,
  Route as RouteIcon,
  ArrowDown,
  Cpu,
} from "lucide-react";
import { num } from "../../utils/formatters";

/**
 * Hero preview panel.
 *
 * Built to look like a slice of the optimizer itself rather than a marketing
 * graphic: the same card shell, the same compact stat blocks and the same
 * blue icon chips the dashboard uses.
 *
 * The three counts are passed in from the live /api/data/status call that the
 * page already makes -- nothing here is a constant. The lower half shows the
 * three decisions the solver produces as labels only; no objective value,
 * store name or runtime appears, because this panel is not a result.
 */

const STEPS = [
  { label: "Store Location", icon: StoreIcon },
  { label: "Demand Assignment", icon: RouteIcon },
  { label: "Inventory Allocation", icon: Boxes },
];

function MiniStat({ icon: Icon, label, value, loading }) {
  return (
    <div className="rounded-md border border-ink-200 bg-ink-50/70 p-3">
      <span className="mb-2 flex h-7 w-7 items-center justify-center rounded-md bg-brand-50 text-brand-600">
        <Icon size={14} />
      </span>
      <div className="text-[10.5px] font-medium uppercase tracking-wide text-ink-400">
        {label}
      </div>
      {loading ? (
        <div className="mt-1 h-6 w-12 animate-pulse rounded bg-ink-200" />
      ) : (
        <div className="tnum mt-0.5 text-[19px] font-semibold leading-tight text-ink-900">
          {value}
        </div>
      )}
    </div>
  );
}

export default function HeroVisual({ counts, loading = false }) {
  return (
    <div className="rounded-lg border border-ink-200 bg-white shadow-[0_1px_3px_rgba(16,24,40,0.07)]">
      {/* panel header, same weight as a dashboard card title */}
      <div className="flex items-center justify-between gap-3 border-b border-ink-200 px-5 py-3.5">
        <div className="flex items-center gap-2.5">
          <span className="flex h-7 w-7 items-center justify-center rounded-md bg-brand-50 text-brand-600">
            <Cpu size={15} />
          </span>
          <div>
            <div className="text-[13.5px] font-semibold leading-tight text-ink-900">
              Optimization Preview
            </div>
            <div className="text-[11.5px] leading-snug text-ink-500">
              Inputs the solver reads, and the decisions it returns
            </div>
          </div>
        </div>
        <span className="hidden shrink-0 rounded-md bg-ink-100 px-2 py-0.5 text-[11px] font-medium text-ink-600 ring-1 ring-inset ring-ink-200 sm:inline">
          Illustrative
        </span>
      </div>

      <div className="p-5">
        <div className="grid grid-cols-3 gap-3">
          <MiniStat
            icon={StoreIcon}
            label="Candidate Stores"
            value={num(counts?.stores)}
            loading={loading}
          />
          <MiniStat
            icon={MapPin}
            label="Demand Areas"
            value={num(counts?.demand_zones)}
            loading={loading}
          />
          <MiniStat
            icon={Boxes}
            label="Products"
            value={num(counts?.products)}
            loading={loading}
          />
        </div>

        <div className="my-4 flex items-center gap-3">
          <div className="h-px flex-1 bg-ink-200" />
          <span className="text-[10.5px] font-medium uppercase tracking-wide text-ink-400">
            Solver output
          </span>
          <div className="h-px flex-1 bg-ink-200" />
        </div>

        <div className="space-y-2">
          {STEPS.map(({ label, icon: Icon }, i) => (
            <div key={label}>
              {i > 0 ? (
                <div className="flex justify-center py-1">
                  <ArrowDown size={13} className="text-ink-300" />
                </div>
              ) : null}
              <div className="flex items-center gap-3 rounded-md border border-ink-200 bg-white px-3.5 py-2.5">
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md bg-brand-50 text-brand-600">
                  <Icon size={14} />
                </span>
                <span className="text-[13px] font-medium text-ink-800">
                  {label}
                </span>
                <span className="ml-auto text-[11px] text-ink-400">
                  0{i + 1}
                </span>
              </div>
            </div>
          ))}
        </div>

        <p className="mt-4 text-[11.5px] leading-relaxed text-ink-400">
          Counts load live from the optimizer API. Objective value, selected
          stores and runtime are produced by an actual run and shown in the
          optimizer, not here.
        </p>
      </div>
    </div>
  );
}
