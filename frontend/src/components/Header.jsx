import { Menu, Wifi, WifiOff, Loader2, RefreshCw } from "lucide-react";
import { API_BASE_URL } from "../services/api";

/**
 * Backend status is NOT faked: it reflects the real result of GET /health,
 * polled by useHealth(). Three states -- checking, online, offline.
 */
export default function Header({ onMenu, health }) {
  const { status, data, error, refresh } = health;

  let indicator;
  if (status === "loading") {
    indicator = (
      <span className="inline-flex items-center gap-1.5 rounded-md bg-ink-100 px-2.5 py-1.5 text-[12px] font-medium text-ink-600 ring-1 ring-inset ring-ink-200">
        <Loader2 size={13} className="animate-spin" />
        Checking backend
      </span>
    );
  } else if (status === "ok") {
    indicator = (
      <span className="inline-flex items-center gap-1.5 rounded-md bg-emerald-50 px-2.5 py-1.5 text-[12px] font-medium text-emerald-700 ring-1 ring-inset ring-emerald-200">
        <span className="relative flex h-1.5 w-1.5">
          <span className="absolute inline-flex h-full w-full rounded-full bg-emerald-500" />
        </span>
        <Wifi size={13} />
        Backend Connected
        {data?.dialect ? (
          <span className="font-normal text-emerald-600">· {data.dialect}</span>
        ) : null}
      </span>
    );
  } else {
    indicator = (
      <button
        onClick={refresh}
        title={error?.message || "Backend unreachable"}
        className="inline-flex items-center gap-1.5 rounded-md bg-red-50 px-2.5 py-1.5 text-[12px] font-medium text-red-700 ring-1 ring-inset ring-red-200 hover:bg-red-100"
      >
        <WifiOff size={13} />
        Backend Offline
        <RefreshCw size={12} />
      </button>
    );
  }

  return (
    <header className="sticky top-0 z-20 border-b border-ink-200 bg-white/95 backdrop-blur">
      <div className="flex items-center gap-3 px-4 py-3 sm:px-6">
        <button
          onClick={onMenu}
          className="rounded-md p-1.5 text-ink-500 hover:bg-ink-100 lg:hidden"
          aria-label="Open navigation"
        >
          <Menu size={19} />
        </button>

        <div className="min-w-0 flex-1">
          <h1 className="truncate text-[15px] font-semibold leading-tight text-ink-900">
            QAOA Dark Store Optimizer
          </h1>
          <p className="truncate text-[12px] text-ink-500">
            Joint Store Location &amp; Inventory Optimization
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span className="hidden text-[11.5px] text-ink-400 xl:inline">
            {API_BASE_URL}
          </span>
          {indicator}
        </div>
      </div>

      {status === "error" ? (
        <div className="border-t border-red-200 bg-red-50 px-4 py-2 text-[12px] text-red-800 sm:px-6">
          <strong className="font-semibold">Backend unreachable.</strong>{" "}
          Check that the FastAPI server is running and reachable at{" "}
          <code className="rounded bg-red-100 px-1 py-0.5 font-mono text-[11px]">
            {API_BASE_URL}
          </code>
          . That address comes from{" "}
          <code className="font-mono text-[11px]">VITE_API_BASE_URL</code> in{" "}
          <code className="font-mono text-[11px]">frontend/.env</code>; Vite
          reads it at startup, so restart the dev server after changing it.
          Data and optimization are unavailable until the backend responds.
        </div>
      ) : null}
    </header>
  );
}
