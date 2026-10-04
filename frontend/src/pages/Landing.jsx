import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import {
  ArrowRight,
  ArrowDown,
  Database,
  Cpu,
  GitCompare,
  ShieldCheck,
  Route as RouteIcon,
  Boxes,
  MapPin,
  Store as StoreIcon,
  Layers,
  FlaskConical,
  Sigma,
  Settings2,
  Gauge,
  CheckCircle2,
  Wallet,
} from "lucide-react";
import LandingNav from "../components/landing/LandingNav";
import HeroVisual from "../components/landing/HeroVisual";
import StatCard from "../components/StatCard";
import { Badge, Card, Note } from "../components/Primitives";
import api, { toFriendlyError } from "../services/api";
import {
  DASH,
  money,
  num,
  pct,
  pctRaw,
  seconds,
} from "../utils/formatters";

/* ------------------------------------------------------------------ bits */

/**
 * Scroll-entry wrapper. The element is visible by default and the observer
 * only adds the settled state, so if JS is slow, IntersectionObserver is
 * missing, or the visitor prefers reduced motion, the content still shows.
 */
function Reveal({ children, className = "", delay = 0 }) {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (typeof IntersectionObserver === "undefined") {
      el.classList.add("is-in");
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.classList.add("is-in");
            io.unobserve(entry.target);
          }
        }
      },
      { threshold: 0.08, rootMargin: "0px 0px -8% 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`lp-reveal ${className}`}
      style={delay ? { transitionDelay: `${delay}ms` } : undefined}
    >
      {children}
    </div>
  );
}

/** Section label, matching the dashboard's uppercase meta type. */
function Eyebrow({ children }) {
  return (
    <div className="mb-2 text-[11.5px] font-semibold uppercase tracking-wide text-brand-600">
      {children}
    </div>
  );
}

function SectionHead({ eyebrow, title, body, className = "" }) {
  return (
    <div className={`max-w-2xl ${className}`}>
      {eyebrow ? <Eyebrow>{eyebrow}</Eyebrow> : null}
      <h2 className="text-[1.5rem] font-semibold leading-tight tracking-tight text-ink-900 sm:text-[1.8rem]">
        {title}
      </h2>
      {body ? (
        <p className="mt-3 text-[14px] leading-relaxed text-ink-600">{body}</p>
      ) : null}
    </div>
  );
}

/** Page section on the dashboard's canvas colour. */
function Section({ id, children, className = "", alt = false }) {
  return (
    <section
      id={id}
      className={`scroll-mt-20 px-4 py-16 sm:px-6 sm:py-20 ${
        alt ? "border-y border-ink-200 bg-white" : ""
      } ${className}`}
    >
      <div className="mx-auto max-w-7xl">{children}</div>
    </section>
  );
}

/** Blue icon chip, identical to StatCard / SectionTitle accents. */
function IconChip({ icon: Icon, size = 17 }) {
  return (
    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-brand-50 text-brand-600">
      <Icon size={size} />
    </span>
  );
}

/* ------------------------------------------------------------- data hooks */

/** Live counts. Never falls back to constants -- an error stays an error. */
function useDataStatus() {
  const [state, setState] = useState("loading");
  const [data, setData] = useState(null);

  useEffect(() => {
    let alive = true;
    api
      .get("/api/data/status")
      .then((r) => {
        if (!alive) return;
        setData(r.data || null);
        setState("ok");
      })
      .catch((err) => {
        if (!alive) return;
        toFriendlyError(err);
        setState("error");
      });
    return () => {
      alive = false;
    };
  }, []);

  return { state, counts: data?.counts || null, routing: data?.routing || null };
}

/**
 * The most recent COMPLETED run's comparison, read from the existing API.
 *
 * Nothing is computed here and nothing is invented: if no completed run exists
 * or the request fails, the table renders the metric names with em dashes
 * rather than placeholder numbers.
 */
function useLatestComparison() {
  const [state, setState] = useState("loading");
  const [runId, setRunId] = useState(null);
  const [cmp, setCmp] = useState(null);

  useEffect(() => {
    let alive = true;
    (async () => {
      try {
        const res = await api.get("/api/optimization/runs", {
          params: { limit: 10 },
        });
        const runs = Array.isArray(res.data) ? res.data : res.data?.runs || [];
        const done = runs.find((r) => r.status === "completed");
        if (!done) {
          if (alive) setState("empty");
          return;
        }
        const c = await api.get(`/api/optimization/${done.id}/comparison`);
        if (!alive) return;
        setRunId(done.id);
        setCmp(c.data || null);
        setState("ok");
      } catch (err) {
        if (!alive) return;
        toFriendlyError(err);
        setState("error");
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  return { state, runId, cmp };
}

/* --------------------------------------------------- comparison panel */

function ComparisonPanel() {
  const { state, runId, cmp } = useLatestComparison();

  const cell = (solver, key) => {
    if (state !== "ok" || !cmp?.[solver]) return DASH;
    const s = cmp[solver];
    switch (key) {
      case "objective_value":
        return money(s.objective_value);
      case "runtime":
        return seconds(s.runtime);
      case "customers_served":
        return num(s.customers_served);
      case "service_level":
        return pct(s.service_level);
      case "gap":
        return pctRaw(cmp.optimality_gap_percent?.[solver]);
      case "violations":
        return num((s.constraint_violations || []).length);
      default:
        return DASH;
    }
  };

  const rows = [
    { key: "objective_value", label: "Objective value" },
    { key: "runtime", label: "Runtime" },
    { key: "customers_served", label: "Demand served" },
    { key: "service_level", label: "Coverage" },
    { key: "gap", label: "Optimality gap" },
    { key: "violations", label: "Constraint violations" },
  ];

  return (
    <Card padded={false}>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-ink-200 px-5 py-3.5">
        <div className="flex items-center gap-2.5">
          <IconChip icon={GitCompare} size={15} />
          <div>
            <div className="text-[13.5px] font-semibold leading-tight text-ink-900">
              Solver comparison
            </div>
            <div className="text-[11.5px] leading-snug text-ink-500">
              {state === "ok"
                ? `Latest completed run #${runId}`
                : state === "loading"
                  ? "Loading latest run…"
                  : state === "empty"
                    ? "No completed run yet"
                    : "Latest run unavailable"}
            </div>
          </div>
        </div>
        {state === "ok" ? (
          <Badge tone="info">Measured</Badge>
        ) : state === "loading" ? (
          <Badge tone="neutral">Loading</Badge>
        ) : (
          <Badge tone="neutral">Preview</Badge>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[420px] border-collapse text-[13px]">
          <thead>
            <tr className="border-b border-ink-200 text-left">
              <th className="px-5 pb-2 pt-3 font-medium text-ink-500">Metric</th>
              <th className="px-5 pb-2 pt-3 text-right font-medium text-ink-500">
                QAOA
              </th>
              <th className="px-5 pb-2 pt-3 text-right font-medium text-ink-500">
                Classical
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ key, label }) => (
              <tr key={key} className="border-b border-ink-100 last:border-0">
                <td className="px-5 py-2.5 text-ink-700">{label}</td>
                <td className="tnum px-5 py-2.5 text-right font-medium text-ink-900">
                  {state === "loading" ? (
                    <span className="inline-block h-4 w-16 animate-pulse rounded bg-ink-100 align-middle" />
                  ) : (
                    cell("qaoa", key)
                  )}
                </td>
                <td className="tnum px-5 py-2.5 text-right font-medium text-ink-900">
                  {state === "loading" ? (
                    <span className="inline-block h-4 w-16 animate-pulse rounded bg-ink-100 align-middle" />
                  ) : (
                    cell("classical", key)
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="border-t border-ink-200 px-5 py-3.5">
        <p className="text-[11.5px] leading-relaxed text-ink-500">
          {state === "ok"
            ? "Values are read from an actual completed run via the optimizer API. Run the optimizer to produce your own."
            : "Values appear once a run has completed. Nothing is shown here until the API returns a real result."}
        </p>
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------- the page */

export default function Landing() {
  const { state, counts, routing } = useDataStatus();

  const metrics = [
    { key: "stores", label: "Candidate Stores", icon: StoreIcon, accent: "brand" },
    { key: "demand_zones", label: "Demand Zones", icon: MapPin, accent: "violet" },
    { key: "products", label: "Products", icon: Boxes, accent: "emerald" },
    { key: "travel_times", label: "Travel Legs", icon: RouteIcon, accent: "brand" },
    { key: "demand_rows", label: "Demand Rows", icon: Layers, accent: "ink" },
  ];

  const problems = [
    {
      tag: "Store Location",
      icon: StoreIcon,
      body: "Where should a new store be opened?",
    },
    {
      tag: "Customer Assignment",
      icon: RouteIcon,
      body: "Which demand area should each store serve?",
    },
    {
      tag: "Inventory",
      icon: Boxes,
      body: "How much stock should each store hold?",
    },
    {
      tag: "Constraints",
      icon: Wallet,
      body: "Can budget, storage, and delivery limits be satisfied?",
    },
  ];

  const steps = [
    {
      n: "01",
      tag: "Data",
      icon: Database,
      body: "Collect geographic, product, demand and routing data.",
    },
    {
      n: "02",
      tag: "QUBO",
      icon: Sigma,
      body: "Formulate the store-location and inventory problem as a QUBO.",
    },
    {
      n: "03",
      tag: "QAOA",
      icon: Cpu,
      body: "Solve the optimization problem using QAOA.",
    },
    {
      n: "04",
      tag: "Validate",
      icon: ShieldCheck,
      body: "Compare against classical optimization and independently validate constraints.",
    },
  ];

  const outputs = [
    {
      n: "01",
      tag: "Selected Stores",
      icon: StoreIcon,
      body: "Determine which candidate locations should be opened.",
    },
    {
      n: "02",
      tag: "Customer Assignments",
      icon: RouteIcon,
      body: "Determine which store serves each demand area.",
    },
    {
      n: "03",
      tag: "Inventory Allocation",
      icon: Boxes,
      body: "Determine how much stock to keep at each selected store.",
    },
  ];

  const flow = [
    "Candidate Stores",
    "Selected Stores",
    "Customer Assignments",
    "Inventory Allocation",
  ];

  /* Provenance keeps the dashboard's own badge tones, which readers of the
     DataSources panel will already recognise. */
  const provenance = [
    {
      label: "Real / Public Data",
      tone: "success",
      icon: ShieldCheck,
      items: [
        "OpenStreetMap",
        "Blinkit public product catalogue",
        "OSRM road routing",
      ],
    },
    {
      label: "Proxy / Estimated",
      tone: "warning",
      icon: Sigma,
      items: ["Population-derived demand"],
    },
    {
      label: "Modelling Assumptions",
      tone: "neutral",
      icon: FlaskConical,
      items: [
        "Opening cost",
        "Storage capacity",
        "Delivery / rider assumptions",
        "Economic parameters",
      ],
    },
  ];

  const tech = [
    "QUBO", "QAOA", "Qiskit", "Python", "FastAPI", "React",
    "Supabase", "PostgreSQL", "OpenStreetMap", "OSRM", "PuLP / CBC",
  ];

  const capabilities = [
    { label: "Configurable constraints", icon: Settings2 },
    { label: "QAOA circuit depth and shots", icon: Gauge },
    { label: "Independent constraint validation", icon: ShieldCheck },
    { label: "Full data provenance", icon: Database },
  ];

  return (
    <div className="min-h-screen bg-canvas">
      <LandingNav />

      {/* ================================================== HERO ========= */}
      <section
        id="top"
        className="relative overflow-hidden border-b border-ink-200 bg-gradient-to-b from-brand-50/70 via-canvas to-canvas px-4 py-16 sm:px-6 sm:py-20"
      >
        <div
          aria-hidden="true"
          className="lp-grid-drift pointer-events-none absolute inset-0 opacity-[0.5]"
          style={{
            backgroundImage:
              "linear-gradient(to right,#dde1e9 1px,transparent 1px),linear-gradient(to bottom,#dde1e9 1px,transparent 1px)",
            backgroundSize: "56px 56px",
            maskImage:
              "radial-gradient(70% 60% at 30% 0%, #000 0%, transparent 75%)",
            WebkitMaskImage:
              "radial-gradient(70% 60% at 30% 0%, #000 0%, transparent 75%)",
          }}
        />

        <div className="relative mx-auto grid max-w-7xl items-center gap-10 lg:grid-cols-[1.05fr_1fr] lg:gap-14">
          <Reveal>
            <Badge tone="info">
              <span className="h-1.5 w-1.5 rounded-full bg-brand-500" />
              Quantum Optimization • Real-World Data
            </Badge>

            <h1 className="mt-4 text-[2rem] font-semibold leading-[1.12] tracking-tight text-ink-900 sm:text-[2.6rem] lg:text-[2.9rem]">
              Smarter Dark-Store
              <br />
              Decisions with <span className="text-brand-600">QAOA</span>
            </h1>

            <p className="mt-4 max-w-xl text-[14.5px] leading-relaxed text-ink-600">
              Optimize store locations, customer assignments, and inventory
              allocation using QUBO, QAOA, and real geographic routing data.
            </p>

            <div className="mt-7 flex flex-wrap gap-3">
              <Link
                to="/optimizer"
                className="inline-flex items-center justify-center gap-2 rounded-md bg-brand-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-[0_1px_2px_rgba(16,24,40,0.08)] transition hover:bg-brand-700"
              >
                Launch Optimizer
                <ArrowRight size={15} />
              </Link>
              <a
                href="#how-it-works"
                className="inline-flex items-center justify-center gap-2 rounded-md border border-ink-300 bg-white px-4 py-2.5 text-[13.5px] font-medium text-ink-700 transition hover:bg-ink-50"
              >
                Explore Methodology
              </a>
            </div>

            {state === "ok" && routing?.all_real_routes ? (
              <div className="mt-6 inline-flex items-center gap-1.5 rounded-md bg-emerald-50 px-2.5 py-1.5 text-[12px] font-medium text-emerald-700 ring-1 ring-inset ring-emerald-200">
                <CheckCircle2 size={13} />
                All travel legs routed on real road geometry
              </div>
            ) : null}
          </Reveal>

          <Reveal delay={100}>
            <HeroVisual counts={counts} loading={state === "loading"} />
          </Reveal>
        </div>
      </section>

      {/* =============================================== METRICS ========= */}
      <Section id="data" alt>
        <Reveal>
          <SectionHead
            eyebrow="Built on Real Public Data"
            title="What the optimizer is working from."
            body="Geographic and routing inputs come from publicly available sources. Demand is represented using a documented population-derived proxy."
            className="mb-8"
          />
        </Reveal>

        {state === "error" ? (
          <Reveal>
            <Note tone="warning">
              <strong className="font-semibold">
                Data currently unavailable.
              </strong>{" "}
              The backend is not responding. These figures load live from the
              optimizer API and are left blank rather than shown from memory.
            </Note>
          </Reveal>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
            {metrics.map(({ key, label, icon, accent }, i) => (
              <Reveal key={key} delay={i * 60}>
                <StatCard
                  icon={icon}
                  label={label}
                  value={num(counts?.[key])}
                  accent={accent}
                  loading={state === "loading"}
                />
              </Reveal>
            ))}
          </div>
        )}
      </Section>

      {/* =============================================== PROBLEM ========= */}
      <Section id="problem">
        <Reveal>
          <SectionHead
            eyebrow="The Problem"
            title="One decision. Multiple constraints."
            body="Store placement, demand assignment and stock levels are not independent choices. Our system formulates them jointly as a QUBO and solves it with QAOA, alongside a classical optimization baseline."
            className="mb-8"
          />
        </Reveal>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {problems.map(({ tag, body, icon }, i) => (
            <Reveal key={tag} delay={i * 70}>
              <Card className="lp-card h-full">
                <IconChip icon={icon} />
                <h3 className="mt-3.5 text-[11.5px] font-semibold uppercase tracking-wide text-ink-400">
                  {tag}
                </h3>
                <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-700">
                  {body}
                </p>
              </Card>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* ========================================== HOW IT WORKS ========= */}
      <Section id="how-it-works" alt>
        <Reveal>
          <SectionHead
            eyebrow="Methodology"
            title="How the Optimizer Works"
            body="Four stages, from public data to a validated decision."
            className="mb-8"
          />
        </Reveal>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {steps.map(({ n, tag, body, icon }, i) => (
            <Reveal key={n} delay={i * 70}>
              <Card className="lp-card h-full">
                <div className="flex items-start justify-between gap-3">
                  <IconChip icon={icon} />
                  <span className="tnum text-[13px] font-semibold text-ink-300">
                    {n}
                  </span>
                </div>
                <h3 className="mt-3.5 text-[11.5px] font-semibold uppercase tracking-wide text-ink-400">
                  {tag}
                </h3>
                <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-700">
                  {body}
                </p>
              </Card>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* ============================================== OUTPUTS ========== */}
      <Section id="outputs">
        <Reveal>
          <SectionHead
            eyebrow="Output"
            title="From Data to Decisions"
            body="Three decisions, solved together rather than one after another."
            className="mb-8"
          />
        </Reveal>

        <div className="grid gap-4 md:grid-cols-3">
          {outputs.map(({ n, tag, body, icon }, i) => (
            <Reveal key={n} delay={i * 70}>
              <Card className="lp-card h-full">
                <div className="flex items-start justify-between gap-3">
                  <IconChip icon={icon} size={19} />
                  <span className="tnum text-[13px] font-semibold text-ink-300">
                    {n}
                  </span>
                </div>
                <h3 className="mt-3.5 text-[11.5px] font-semibold uppercase tracking-wide text-ink-400">
                  {tag}
                </h3>
                <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-700">
                  {body}
                </p>
              </Card>
            </Reveal>
          ))}
        </div>

        <Reveal delay={100}>
          <div className="mt-6 rounded-lg border border-ink-200 bg-white p-5 shadow-[0_1px_2px_rgba(16,24,40,0.05)]">
            <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center sm:gap-3">
              {flow.map((label, i) => (
                <div
                  key={label}
                  className="flex flex-col items-center gap-2 sm:flex-row sm:gap-3"
                >
                  {i > 0 ? (
                    <>
                      <ArrowDown size={14} className="text-ink-300 sm:hidden" />
                      <ArrowRight
                        size={14}
                        className="hidden text-ink-300 sm:block"
                      />
                    </>
                  ) : null}
                  <span
                    className={`w-full whitespace-nowrap rounded-md border px-3 py-1.5 text-center text-[12.5px] sm:w-auto ${
                      i === 0
                        ? "border-ink-300 bg-white text-ink-600"
                        : "border-brand-200 bg-brand-50 font-medium text-brand-700"
                    }`}
                  >
                    {label}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </Reveal>
      </Section>

      {/* ==================================== QAOA VS CLASSICAL ========== */}
      <Section id="comparison" alt>
        <div className="grid items-start gap-10 lg:grid-cols-[1fr_1.05fr] lg:gap-14">
          <Reveal>
            <SectionHead
              eyebrow="Experimental Comparison"
              title="QAOA vs Classical Optimization"
              body="The same optimization instance is evaluated using QAOA and a classical optimization solver."
            />
            <p className="mt-4 text-[14px] leading-relaxed text-ink-600">
              Both solvers receive identical inputs and both solutions are
              checked by the same independent validator, so the figures sit on
              the same footing.
            </p>
            <div className="mt-5">
              <Note tone="info">
                QAOA is a sampling heuristic and gives no optimality guarantee.
                The classical solver provides the reference baseline. No claim
                is made on this page about which performs better — read the
                measured values.
              </Note>
            </div>
            <Link
              to="/optimizer"
              className="mt-6 inline-flex items-center justify-center gap-2 rounded-md bg-brand-600 px-4 py-2.5 text-[13.5px] font-medium text-white shadow-[0_1px_2px_rgba(16,24,40,0.08)] transition hover:bg-brand-700"
            >
              View Live Comparison
              <ArrowRight size={15} />
            </Link>
          </Reveal>

          <Reveal delay={100}>
            <ComparisonPanel />
          </Reveal>
        </div>
      </Section>

      {/* ========================================= METHODOLOGY =========== */}
      <Section id="methodology">
        <Reveal>
          <SectionHead
            eyebrow="Data Transparency"
            title="What is measured, and what is assumed."
            body="Every input is labelled by provenance. Real observations and modelling assumptions are never presented as the same thing."
            className="mb-8"
          />
        </Reveal>

        <div className="grid gap-4 lg:grid-cols-3">
          {provenance.map(({ label, tone, icon: Icon, items }, i) => (
            <Reveal key={label} delay={i * 70}>
              <Card className="lp-card h-full">
                <div className="mb-3.5 flex flex-wrap items-center gap-2.5">
                  <IconChip icon={Icon} size={15} />
                  <Badge tone={tone}>{label}</Badge>
                </div>
                <ul className="space-y-2">
                  {items.map((it) => (
                    <li key={it} className="flex items-start gap-2.5">
                      <span className="mt-[7px] h-1.5 w-1.5 shrink-0 rounded-full bg-ink-300" />
                      <span className="text-[13.5px] leading-snug text-ink-700">
                        {it}
                      </span>
                    </li>
                  ))}
                </ul>
              </Card>
            </Reveal>
          ))}
        </div>

        <div className="mt-6 space-y-3">
          {[
            "Candidate locations sourced from OpenStreetMap are treated as candidate retail locations and are not claimed to be verified operating dark stores.",
            "Demand is a population-derived proxy, not observed customer order data.",
          ].map((t, i) => (
            <Reveal key={t} delay={i * 70}>
              <Note tone="warning">{t}</Note>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* ========================================== TECHNOLOGY =========== */}
      <Section id="technology" alt>
        <Reveal>
          <SectionHead
            eyebrow="Technology"
            title="The stack behind the optimizer."
            className="mb-8"
          />
        </Reveal>

        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {tech.map((t, i) => (
            <Reveal key={t} delay={i * 35}>
              <div className="lp-card rounded-lg border border-ink-200 bg-white px-3 py-3 text-center text-[13px] font-medium text-ink-700 shadow-[0_1px_2px_rgba(16,24,40,0.05)]">
                {t}
              </div>
            </Reveal>
          ))}
        </div>

        <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {capabilities.map(({ label, icon: Icon }, i) => (
            <Reveal key={label} delay={i * 60}>
              <div className="flex h-full items-start gap-2.5 rounded-lg border border-ink-200 bg-ink-50/60 px-4 py-3">
                <span className="mt-0.5 shrink-0 text-brand-600">
                  <Icon size={15} />
                </span>
                <span className="text-[13px] leading-snug text-ink-700">
                  {label}
                </span>
              </div>
            </Reveal>
          ))}
        </div>
      </Section>

      {/* ============================================ FINAL CTA ========== */}
      <Section id="cta">
        <Reveal>
          <div className="overflow-hidden rounded-lg border border-brand-200 bg-brand-600 px-6 py-12 text-center shadow-[0_1px_3px_rgba(16,24,40,0.08)] sm:px-10 sm:py-14">
            <div className="mx-auto max-w-2xl">
              <h2 className="text-[1.5rem] font-semibold leading-tight tracking-tight text-white sm:text-[1.9rem]">
                Ready to optimize your store network?
              </h2>
              <p className="mt-3 text-[14px] leading-relaxed text-brand-100">
                Run the optimizer to explore store locations, customer
                assignments, inventory allocation, and QAOA versus classical
                results.
              </p>
              <Link
                to="/optimizer"
                className="mt-7 inline-flex items-center justify-center gap-2 rounded-md bg-white px-5 py-2.5 text-[13.5px] font-semibold text-brand-700 shadow-[0_1px_2px_rgba(16,24,40,0.12)] transition hover:bg-brand-50"
              >
                Launch Optimizer
                <ArrowRight size={15} />
              </Link>
            </div>
          </div>
        </Reveal>
      </Section>

      {/* ============================================== FOOTER =========== */}
      <footer className="border-t border-ink-200 bg-white px-4 py-10 sm:px-6">
        <div className="mx-auto grid max-w-7xl gap-8 sm:grid-cols-2">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="flex h-8 w-8 items-center justify-center rounded-md bg-brand-600 text-white">
                <Atom2 />
              </span>
              <span className="text-[14px] font-semibold text-ink-900">
                QAOA Dark Store Optimizer
              </span>
            </div>
            <p className="mt-2.5 text-[13px] text-ink-600">
              Joint Store Location &amp; Inventory Optimization
            </p>
            <p className="mt-3 text-[12.5px] text-ink-400">
              Built as an AI/quantum optimization research project.
            </p>
          </div>

          <nav className="sm:justify-self-end">
            <div className="mb-3 text-[11.5px] font-semibold uppercase tracking-wide text-ink-400">
              Navigate
            </div>
            <ul className="space-y-2">
              {[
                ["#top", "Home"],
                ["#how-it-works", "How It Works"],
                ["#data", "Data"],
                ["#technology", "Technology"],
              ].map(([href, label]) => (
                <li key={href}>
                  <a
                    href={href}
                    className="text-[13px] text-ink-600 transition hover:text-brand-600"
                  >
                    {label}
                  </a>
                </li>
              ))}
              <li>
                <Link
                  to="/optimizer"
                  className="text-[13px] font-medium text-brand-600 transition hover:text-brand-700"
                >
                  Optimizer
                </Link>
              </li>
            </ul>
          </nav>
        </div>
      </footer>
    </div>
  );
}

/** Small inline mark so the footer does not pull another icon import. */
function Atom2() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <circle cx="12" cy="12" r="1.6" fill="currentColor" stroke="none" />
      <ellipse cx="12" cy="12" rx="10" ry="4.5" />
      <ellipse cx="12" cy="12" rx="10" ry="4.5" transform="rotate(60 12 12)" />
      <ellipse cx="12" cy="12" rx="10" ry="4.5" transform="rotate(120 12 12)" />
    </svg>
  );
}
