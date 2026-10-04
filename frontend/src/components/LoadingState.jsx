import { Loader2 } from "lucide-react";

export default function LoadingState({ label = "Loading...", rows = 0 }) {
  return (
    <div>
      <div className="flex items-center gap-2 text-[13px] text-ink-500">
        <Loader2 size={15} className="animate-spin" />
        {label}
      </div>
      {rows > 0 ? (
        <div className="mt-4 space-y-2">
          {Array.from({ length: rows }).map((_, i) => (
            <div
              key={i}
              className="h-9 animate-pulse rounded-md bg-ink-100"
              style={{ animationDelay: `${i * 80}ms` }}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
