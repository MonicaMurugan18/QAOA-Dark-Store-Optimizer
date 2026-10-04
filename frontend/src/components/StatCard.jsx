import { Badge } from "./Primitives";

const ACCENTS = {
  brand: "bg-brand-50 text-brand-600",
  emerald: "bg-emerald-50 text-emerald-600",
  violet: "bg-violet-50 text-violet-600",
  amber: "bg-amber-50 text-amber-600",
  ink: "bg-ink-100 text-ink-500",
};

export default function StatCard({
  icon: Icon,
  label,
  value,
  hint,
  accent = "brand",
  badge,
  badgeTone = "neutral",
  loading = false,
}) {
  return (
    <div className="rounded-lg border border-ink-200 bg-white p-4 shadow-[0_1px_2px_rgba(16,24,40,0.05)]">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[11.5px] font-medium uppercase tracking-wide text-ink-400">
            {label}
          </div>
          {loading ? (
            <div className="mt-2 h-7 w-20 animate-pulse rounded bg-ink-100" />
          ) : (
            <div
              title={String(value)}
              className="tnum mt-1 text-[22px] font-semibold leading-tight text-ink-900"
            >
              {value}
            </div>
          )}
          {hint && !loading ? (
            <div className="mt-1 truncate text-[11.5px] text-ink-400">{hint}</div>
          ) : null}
        </div>
        {Icon ? (
          <span
            className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-md ${ACCENTS[accent]}`}
          >
            <Icon size={17} />
          </span>
        ) : null}
      </div>
      {badge && !loading ? (
        <div className="mt-3">
          <Badge tone={badgeTone}>{badge}</Badge>
        </div>
      ) : null}
    </div>
  );
}
