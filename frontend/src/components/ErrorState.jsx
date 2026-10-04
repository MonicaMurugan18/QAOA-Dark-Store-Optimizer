import { AlertCircle, RefreshCw } from "lucide-react";
import { Button } from "./Primitives";

/**
 * Renders the friendly error shape produced by toFriendlyError().
 * Field-level validation problems are listed so the user can fix the input.
 */
export default function ErrorState({ error, onRetry, compact = false }) {
  if (!error) return null;
  return (
    <div
      className={`rounded-md border border-red-200 bg-red-50 ${
        compact ? "p-3" : "p-4"
      }`}
    >
      <div className="flex items-start gap-2.5">
        <AlertCircle size={16} className="mt-0.5 shrink-0 text-red-600" />
        <div className="min-w-0 flex-1">
          <div className="text-[13px] font-semibold text-red-900">
            {error.title}
            {error.status ? (
              <span className="ml-2 font-normal text-red-600">
                HTTP {error.status}
              </span>
            ) : null}
          </div>
          <p className="mt-1 text-[12.5px] leading-relaxed text-red-800">
            {error.message}
          </p>
          {error.fields?.length ? (
            <ul className="mt-2 space-y-1">
              {error.fields.map((f, i) => (
                <li key={i} className="text-[12px] text-red-800">
                  <code className="rounded bg-red-100 px-1 py-0.5 font-mono text-[11px]">
                    {f.field || "request"}
                  </code>{" "}
                  {f.message}
                </li>
              ))}
            </ul>
          ) : null}
          {onRetry ? (
            <div className="mt-3">
              <Button variant="secondary" size="sm" icon={RefreshCw} onClick={onRetry}>
                Try again
              </Button>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
