import { Fragment, useEffect, useState } from "react";
import {
  Database,
  ShieldCheck,
  Sigma,
  FlaskConical,
  ExternalLink,
  RefreshCw,
  ChevronDown,
} from "lucide-react";
import { Badge, Button, Card, Note, Row, SectionTitle, Table } from "./Primitives";
import LoadingState from "./LoadingState";
import ErrorState from "./ErrorState";
import api, { toFriendlyError } from "../services/api";
import { num, text } from "../utils/formatters";

/**
 * Data provenance panel.
 *
 * The whole point is that a viewer can tell at a glance which numbers are
 * observed and which are assumptions. Groups are rendered separately and never
 * mixed, and the labels come from the backend rather than being hardcoded here.
 */

const GROUPS = [
  {
    key: "real",
    title: "Real data",
    icon: ShieldCheck,
    tone: "success",
    blurb: "Observed, publicly verifiable, or published by a government body.",
  },
  {
    key: "proxy_estimated",
    title: "Proxy / estimated data",
    icon: Sigma,
    tone: "warning",
    blurb:
      "Derived from real inputs by a documented formula. Not an observation.",
  },
  {
    key: "synthetic",
    title: "Synthetic assumptions",
    icon: FlaskConical,
    tone: "danger",
    blurb:
      "Invented for the prototype. Requires authorised operator data to replace.",
  },
];

const TYPE_TONE = {
  real_public: "success",
  official: "success",
  real_business: "success",
  proxy: "warning",
  estimated: "warning",
  synthetic: "danger",
};

export default function DataSources() {
  const [data, setData] = useState(null);
  const [status, setStatus] = useState(null);
  const [state, setState] = useState("loading");
  const [error, setError] = useState(null);
  const [open, setOpen] = useState(null);

  const load = async () => {
    setState("loading");
    setError(null);
    try {
      const [s, st] = await Promise.all([
        api.get("/api/data/sources").then((r) => r.data),
        api.get("/api/data/status").then((r) => r.data),
      ]);
      setData(s);
      setStatus(st);
      setState("ok");
    } catch (err) {
      setError(toFriendlyError(err));
      setState("error");
    }
  };

  useEffect(() => {
    load();
  }, []);

  if (state === "loading")
    return (
      <Card>
        <LoadingState label="Loading data provenance..." rows={3} />
      </Card>
    );
  if (state === "error")
    return (
      <Card>
        <SectionTitle icon={Database} title="Data Sources" />
        <ErrorState error={error} onRetry={load} />
      </Card>
    );

  const grouped = data?.grouped || {};
  const routing = status?.routing;

  return (
    <Card>
      <SectionTitle
        icon={Database}
        title="Data Sources & Provenance"
        subtitle="Which values are observed, and which are assumptions"
        right={
          <Button variant="secondary" size="sm" icon={RefreshCw} onClick={load}>
            Refresh
          </Button>
        }
      />

      {/* headline counts straight from the database */}
      {status?.counts ? (
        <div className="mb-5 grid gap-3 sm:grid-cols-3 lg:grid-cols-5">
          {[
            ["Stores", status.counts.stores],
            ["Demand zones", status.counts.demand_zones],
            ["Products", status.counts.products],
            ["Travel legs", status.counts.travel_times],
            ["Demand rows", status.counts.demand_rows],
          ].map(([label, value]) => (
            <div
              key={label}
              className="rounded-md border border-ink-200 bg-ink-50/60 p-3"
            >
              <div className="text-[11px] font-medium uppercase tracking-wide text-ink-400">
                {label}
              </div>
              <div className="tnum mt-0.5 text-[18px] font-semibold text-ink-900">
                {num(value)}
              </div>
            </div>
          ))}
        </div>
      ) : null}

      {/* routing honesty: real routes vs estimates */}
      {routing ? (
        <div className="mb-5">
          <Note tone={routing.all_real_routes ? "info" : "warning"}>
            <strong className="font-semibold">Delivery times:</strong>{" "}
            {num(routing.routed_by_osrm)} leg
            {routing.routed_by_osrm === 1 ? "" : "s"} routed over real
            OpenStreetMap road geometry (OSRM)
            {routing.haversine_fallback > 0 ? (
              <>
                , {num(routing.haversine_fallback)} fell back to a straight-line
                estimate and are labelled as such.
              </>
            ) : (
              <>. No straight-line estimates were used.</>
            )}
          </Note>
        </div>
      ) : null}

      {/* the three groups, never mixed */}
      <div className="space-y-5">
        {GROUPS.map(({ key, title, icon: Icon, tone, blurb }) => {
          const rows = grouped[key] || [];
          if (!rows.length) return null;
          return (
            <div key={key}>
              <div className="mb-2 flex items-center gap-2">
                <Icon
                  size={15}
                  className={
                    tone === "success"
                      ? "text-emerald-600"
                      : tone === "warning"
                        ? "text-amber-600"
                        : "text-red-600"
                  }
                />
                <h3 className="text-[13px] font-semibold text-ink-900">{title}</h3>
                <Badge tone={tone}>{rows.length}</Badge>
              </div>
              <p className="mb-2 text-[11.5px] text-ink-400">{blurb}</p>
              <Table
                head={[
                  { label: "Dataset" },
                  { label: "Source" },
                  { label: "Type" },
                  { label: "Date" },
                  { label: "Records", align: "right" },
                  { label: "Status" },
                ]}
              >
                {rows.map((s) => (
                  <Fragment key={s.key}>
                    <Row
                      onClick={() => setOpen(open === s.key ? null : s.key)}
                    >
                      <td className="pr-3 font-medium text-ink-800">
                        {s.dataset}
                        <ChevronDown
                          size={12}
                          className={`ml-1 inline text-ink-400 transition ${
                            open === s.key ? "rotate-180" : ""
                          }`}
                        />
                      </td>
                      <td className="pr-3 text-ink-600">
                        {s.source_url ? (
                          <a
                            href={s.source_url}
                            target="_blank"
                            rel="noreferrer noopener"
                            onClick={(e) => e.stopPropagation()}
                            className="inline-flex items-center gap-1 text-brand-600 hover:underline"
                          >
                            {s.source_name}
                            <ExternalLink size={11} />
                          </a>
                        ) : (
                          text(s.source_name)
                        )}
                      </td>
                      <td className="pr-3">
                        <Badge tone={TYPE_TONE[s.source_type] || "neutral"}>
                          {s.source_type}
                        </Badge>
                      </td>
                      <td className="tnum pr-3 text-ink-600">
                        {text(s.source_date)}
                      </td>
                      <td className="tnum pr-3 text-right text-ink-600">
                        {num(s.record_count)}
                      </td>
                      <td>
                        <Badge
                          tone={s.status === "loaded" ? "success" : "neutral"}
                        >
                          {text(s.status)}
                        </Badge>
                      </td>
                    </Row>
                    {open === s.key ? (
                      <tr className="border-b border-ink-100">
                        <td colSpan={6} className="bg-ink-50/70 px-3 py-3">
                          <p className="text-[12px] leading-relaxed text-ink-600">
                            {s.notes}
                          </p>
                          <div className="mt-2 flex flex-wrap gap-3 text-[11.5px] text-ink-400">
                            {s.licence ? <span>Licence: {s.licence}</span> : null}
                            {s.feeds ? <span>Feeds: {s.feeds}</span> : null}
                            {s.ingested_at ? (
                              <span>
                                Ingested: {new Date(s.ingested_at).toLocaleString()}
                              </span>
                            ) : null}
                          </div>
                        </td>
                      </tr>
                    ) : null}
                  </Fragment>
                ))}
              </Table>
            </div>
          );
        })}
      </div>

      {status?.caveats?.length ? (
        <div className="mt-5">
          <Note tone="warning">
            <strong className="font-semibold">What this system does not know:</strong>
            <ul className="mt-1.5 list-disc space-y-1 pl-4">
              {status.caveats.map((c, i) => (
                <li key={i}>{c}</li>
              ))}
            </ul>
          </Note>
        </div>
      ) : null}

      {status?.demand_mode ? (
        <p className="mt-3 text-[11.5px] text-ink-400">
          Demand mode:{" "}
          <code className="rounded bg-ink-100 px-1 py-0.5 font-mono text-[11px]">
            {status.demand_mode}
          </code>
          . Switch to <code className="font-mono text-[11px]">historical_orders</code>{" "}
          once an authorised order dataset is loaded.
        </p>
      ) : null}
    </Card>
  );
}
