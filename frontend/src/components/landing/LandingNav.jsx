import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Menu, X, ArrowRight, Atom } from "lucide-react";

/**
 * Landing header.
 *
 * Deliberately the same shell as the dashboard's Header: sticky, white with a
 * backdrop blur, a single ink-200 hairline underneath, 15px semibold title and
 * a 12px ink-500 subtitle. A visitor moving from here into /optimizer should
 * not notice the chrome change.
 */

const LINKS = [
  { href: "#top", label: "Home" },
  { href: "#how-it-works", label: "How It Works" },
  { href: "#data", label: "Data" },
  { href: "#technology", label: "Technology" },
];

export default function LandingNav() {
  const [open, setOpen] = useState(false);

  // Close the mobile sheet if the viewport grows past the breakpoint, so the
  // panel can never be left open behind the desktop layout.
  useEffect(() => {
    const mq = window.matchMedia("(min-width: 1024px)");
    const onChange = (e) => {
      if (e.matches) setOpen(false);
    };
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  return (
    <header className="sticky top-0 z-30 border-b border-ink-200 bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center gap-3 px-4 py-3 sm:px-6">
        <Link to="/" className="flex min-w-0 items-center gap-3">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-brand-600 text-white">
            <Atom size={18} />
          </span>
          <span className="min-w-0">
            <span className="block truncate text-[15px] font-semibold leading-tight text-ink-900">
              QAOA Dark Store Optimizer
            </span>
            <span className="hidden truncate text-[12px] text-ink-500 sm:block">
              Joint Store Location &amp; Inventory Optimization
            </span>
          </span>
        </Link>

        <nav className="ml-auto hidden items-center gap-1 lg:flex">
          {LINKS.map((l) => (
            <a
              key={l.href}
              href={l.href}
              className="rounded-md px-3 py-2 text-[13px] text-ink-600 transition hover:bg-ink-100 hover:text-ink-900"
            >
              {l.label}
            </a>
          ))}
          <Link
            to="/optimizer"
            className="ml-2 inline-flex items-center justify-center gap-2 rounded-md bg-brand-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-[0_1px_2px_rgba(16,24,40,0.08)] transition hover:bg-brand-700"
          >
            Launch Optimizer
            <ArrowRight size={15} />
          </Link>
        </nav>

        <button
          onClick={() => setOpen((v) => !v)}
          className="ml-auto rounded-md p-1.5 text-ink-500 transition hover:bg-ink-100 lg:hidden"
          aria-label="Toggle navigation"
          aria-expanded={open}
        >
          {open ? <X size={19} /> : <Menu size={19} />}
        </button>
      </div>

      {open ? (
        <div className="border-t border-ink-200 bg-white px-4 py-3 sm:px-6 lg:hidden">
          <div className="flex flex-col gap-1">
            {LINKS.map((l) => (
              <a
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className="rounded-md px-3 py-2.5 text-[13.5px] text-ink-600 transition hover:bg-ink-100 hover:text-ink-900"
              >
                {l.label}
              </a>
            ))}
            <Link
              to="/optimizer"
              onClick={() => setOpen(false)}
              className="mt-1 inline-flex items-center justify-center gap-2 rounded-md bg-brand-600 px-4 py-2.5 text-[13.5px] font-medium text-white transition hover:bg-brand-700"
            >
              Launch Optimizer
              <ArrowRight size={15} />
            </Link>
          </div>
        </div>
      ) : null}
    </header>
  );
}
