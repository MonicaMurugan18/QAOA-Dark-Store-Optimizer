/**
 * Small shared building blocks: Card, SectionTitle, Badge, Table shell.
 * Kept in one file so the visual language stays consistent.
 */
import { AlertTriangle, Info } from "lucide-react";

export function Card({ children, className = "", padded = true }) {
  return (
    <div
      className={`rounded-lg border border-ink-200 bg-white shadow-[0_1px_2px_rgba(16,24,40,0.05)] ${
        padded ? "p-5" : ""
      } ${className}`}
    >
      {children}
    </div>
  );
}

export function SectionTitle({ icon: Icon, title, subtitle, right }) {
  return (
    <div className="mb-4 flex items-start justify-between gap-4">
      <div className="flex items-start gap-3">
        {Icon ? (
          <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-brand-50 text-brand-600">
            <Icon size={17} />
          </span>
        ) : null}
        <div>
          <h2 className="text-[15px] font-semibold leading-tight text-ink-900">
            {title}
          </h2>
          {subtitle ? (
            <p className="mt-0.5 text-[13px] leading-snug text-ink-500">
              {subtitle}
            </p>
          ) : null}
        </div>
      </div>
      {right ? <div className="shrink-0">{right}</div> : null}
    </div>
  );
}

const BADGE_TONES = {
  neutral: "bg-ink-100 text-ink-600 ring-ink-200",
  success: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  warning: "bg-amber-50 text-amber-700 ring-amber-200",
  danger: "bg-red-50 text-red-700 ring-red-200",
  info: "bg-brand-50 text-brand-700 ring-brand-200",
  violet: "bg-violet-50 text-violet-700 ring-violet-200",
};

export function Badge({ tone = "neutral", children, className = "" }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset ${
        BADGE_TONES[tone] || BADGE_TONES.neutral
      } ${className}`}
    >
      {children}
    </span>
  );
}

export function Table({ head, children, dense = false }) {
  return (
    <div className="-mx-5 overflow-x-auto px-5">
      <table className="w-full min-w-[520px] border-collapse text-[13px]">
        <thead>
          <tr className="border-b border-ink-200 text-left">
            {head.map((h) => (
              <th
                key={h.key || h.label}
                className={`whitespace-nowrap pb-2 pr-3 font-medium text-ink-500 last:pr-0 ${
                  h.align === "right" ? "text-right" : ""
                } ${h.className || ""}`}
              >
                {h.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className={dense ? "" : "[&_td]:py-2.5"}>{children}</tbody>
      </table>
    </div>
  );
}

export function Row({ children, onClick, active = false }) {
  return (
    <tr
      onClick={onClick}
      className={`border-b border-ink-100 last:border-0 ${
        onClick ? "cursor-pointer hover:bg-ink-50" : ""
      } ${active ? "bg-brand-50/60" : ""}`}
    >
      {children}
    </tr>
  );
}

/** A labelled key/value pair used inside result cards. */
export function Metric({ label, value, hint, tone = "neutral" }) {
  const toneText = {
    neutral: "text-ink-900",
    success: "text-emerald-700",
    warning: "text-amber-700",
    danger: "text-red-700",
  }[tone];
  return (
    <div>
      <div className="text-[11px] font-medium uppercase tracking-wide text-ink-400">
        {label}
      </div>
      <div className={`tnum mt-1 text-[19px] font-semibold ${toneText}`}>
        {value}
      </div>
      {hint ? (
        <div className="mt-0.5 text-[11.5px] leading-snug text-ink-400">
          {hint}
        </div>
      ) : null}
    </div>
  );
}

/** Informational callout. Used for honest caveats, not decoration. */
export function Note({ children, tone = "info", icon }) {
  const tones = {
    info: "border-brand-200 bg-brand-50/60 text-brand-900",
    warning: "border-amber-200 bg-amber-50 text-amber-900",
    danger: "border-red-200 bg-red-50 text-red-900",
  };
  const Icon = icon || (tone === "info" ? Info : AlertTriangle);
  return (
    <div
      className={`flex items-start gap-2.5 rounded-md border px-3 py-2.5 text-[12.5px] leading-relaxed ${tones[tone]}`}
    >
      <Icon size={15} className="mt-0.5 shrink-0" />
      <div>{children}</div>
    </div>
  );
}

export function Field({ label, hint, children, error }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[12.5px] font-medium text-ink-700">
        {label}
      </span>
      {children}
      {error ? (
        <span className="mt-1 block text-[11.5px] text-red-600">{error}</span>
      ) : hint ? (
        <span className="mt-1 block text-[11.5px] text-ink-400">{hint}</span>
      ) : null}
    </label>
  );
}

export function NumberInput({ value, onChange, error, suffix, ...rest }) {
  return (
    <div className="relative">
      <input
        type="number"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className={`tnum w-full rounded-md border bg-white px-3 py-2 text-[13.5px] text-ink-900 outline-none transition focus:ring-2 ${
          error
            ? "border-red-300 focus:border-red-400 focus:ring-red-100"
            : "border-ink-300 focus:border-brand-400 focus:ring-brand-100"
        } ${suffix ? "pr-14" : ""}`}
        {...rest}
      />
      {suffix ? (
        <span className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-[12px] text-ink-400">
          {suffix}
        </span>
      ) : null}
    </div>
  );
}

export function Button({
  children,
  variant = "primary",
  size = "md",
  icon: Icon,
  ...rest
}) {
  const variants = {
    primary:
      "bg-brand-600 text-white hover:bg-brand-700 disabled:bg-brand-300 shadow-[0_1px_2px_rgba(16,24,40,0.08)]",
    secondary:
      "bg-white text-ink-700 border border-ink-300 hover:bg-ink-50 disabled:text-ink-400",
    ghost: "text-ink-600 hover:bg-ink-100 disabled:text-ink-300",
  };
  const sizes = {
    sm: "px-2.5 py-1.5 text-[12.5px]",
    md: "px-4 py-2.5 text-[13.5px]",
  };
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 rounded-md font-medium transition disabled:cursor-not-allowed ${variants[variant]} ${sizes[size]}`}
      {...rest}
    >
      {Icon ? <Icon size={15} /> : null}
      {children}
    </button>
  );
}
