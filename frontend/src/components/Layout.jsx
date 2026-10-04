import { useState } from "react";
import { Outlet } from "react-router-dom";
import Sidebar from "./Sidebar";
import Header from "./Header";
import { useHealth } from "../hooks/useOptimization";

export default function Layout() {
  const [navOpen, setNavOpen] = useState(false);
  const health = useHealth();

  return (
    <div className="min-h-full bg-ink-50">
      <Sidebar open={navOpen} onClose={() => setNavOpen(false)} />
      <div className="lg:pl-64">
        <Header onMenu={() => setNavOpen(true)} health={health} />
        <main className="px-4 py-5 sm:px-6 sm:py-6">
          <Outlet context={{ health }} />
        </main>
        <footer className="border-t border-ink-200 px-4 py-4 text-[11.5px] text-ink-400 sm:px-6">
          QUBO → QAOA (Qiskit statevector simulator) → independent validation →
          classical PuLP/CBC baseline. Operating costs, capacities and demand in
          this dataset are labelled demo assumptions, not observed operator data.
        </footer>
      </div>
    </div>
  );
}
