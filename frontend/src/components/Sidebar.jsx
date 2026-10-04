import { NavLink } from "react-router-dom";
import {
  Atom,
  LayoutDashboard,
  Store,
  Package,
  BarChart3,
  History,
  X,
  ArrowLeft,
} from "lucide-react";

const NAV = [
  { to: "/optimizer", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/stores", label: "Stores", icon: Store },
  { to: "/demand", label: "Demand", icon: BarChart3 },
  { to: "/products", label: "Products", icon: Package },
  { to: "/history", label: "Optimization History", icon: History },
];

export default function Sidebar({ open, onClose }) {
  return (
    <>
      {/* Backdrop, tablet and below */}
      {open ? (
        <div
          className="fixed inset-0 z-30 bg-ink-950/50 lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      ) : null}

      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-64 flex-col bg-ink-900 transition-transform duration-200 lg:translate-x-0 ${
          open ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex items-center gap-2.5 border-b border-white/10 px-5 py-4">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-brand-500 text-white">
            <Atom size={18} />
          </span>
          <div className="min-w-0 flex-1">
            <div className="text-[13px] font-semibold tracking-wide text-white">
              QAOA OPTIMIZER
            </div>
            <div className="text-[10.5px] uppercase tracking-wider text-ink-400">
              Quick commerce
            </div>
          </div>
          <button
            onClick={onClose}
            className="text-ink-400 hover:text-white lg:hidden"
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        </div>

        <nav className="flex-1 overflow-y-auto px-3 py-4">
          <div className="mb-2 px-2 text-[10.5px] font-semibold uppercase tracking-wider text-ink-500">
            Navigation
          </div>
          <ul className="space-y-0.5">
            {NAV.map(({ to, label, icon: Icon, end }) => (
              <li key={to}>
                <NavLink
                  to={to}
                  end={end}
                  onClick={onClose}
                  className={({ isActive }) =>
                    `flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[13px] transition ${
                      isActive
                        ? "bg-brand-600 font-medium text-white"
                        : "text-ink-300 hover:bg-white/5 hover:text-white"
                    }`
                  }
                >
                  <Icon size={16} className="shrink-0" />
                  <span className="truncate">{label}</span>
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>

        <div className="border-t border-white/10 px-3 py-3">
          <NavLink
            to="/"
            onClick={onClose}
            className="flex items-center gap-2.5 rounded-md px-2.5 py-2 text-[12.5px] text-ink-400 transition hover:bg-white/5 hover:text-white"
          >
            <ArrowLeft size={15} className="shrink-0" />
            Back to overview
          </NavLink>
          <p className="mt-2 px-2.5 text-[11px] leading-relaxed text-ink-500">
            QUBO → QAOA → independent validation → classical baseline
          </p>
        </div>
      </aside>
    </>
  );
}
