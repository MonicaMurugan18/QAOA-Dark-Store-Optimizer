import { useMemo, useState } from "react";
import { Store as StoreIcon, Search, X } from "lucide-react";
import { Badge, Card, Row, SectionTitle, Table } from "../components/Primitives";
import LoadingState from "../components/LoadingState";
import ErrorState from "../components/ErrorState";
import EmptyState from "../components/EmptyState";
import { useStores } from "../hooks/useOptimization";
import { money, num, text } from "../utils/formatters";

export default function Stores() {
  const { data, status, error, refresh } = useStores();
  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState(null);

  const rows = useMemo(() => {
    const list = data || [];
    if (!query.trim()) return list;
    const q = query.toLowerCase();
    return list.filter(
      (s) =>
        s.name?.toLowerCase().includes(q) ||
        s.area?.toLowerCase().includes(q) ||
        s.platform?.toLowerCase().includes(q),
    );
  }, [data, query]);

  return (
    <div className="space-y-6">
      <Card>
        <SectionTitle
          icon={StoreIcon}
          title="Candidate Dark Stores"
          subtitle="Every field below is returned by GET /api/stores"
          right={
            status === "ok" ? (
              <Badge tone="info">{(data || []).length} stores</Badge>
            ) : null
          }
        />

        {status === "loading" ? (
          <LoadingState label="Loading stores..." rows={5} />
        ) : status === "error" ? (
          <ErrorState error={error} onRetry={refresh} />
        ) : !rows.length && !query ? (
          <EmptyState
            icon={StoreIcon}
            title="No stores found"
            message="The backend returned no stores. Load the seed data first."
          />
        ) : (
          <>
            <div className="relative mb-4 max-w-sm">
              <Search
                size={15}
                className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400"
              />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Search name, area or platform"
                className="w-full rounded-md border border-ink-300 bg-white py-2 pl-9 pr-9 text-[13px] outline-none focus:border-brand-400 focus:ring-2 focus:ring-brand-100"
              />
              {query ? (
                <button
                  onClick={() => setQuery("")}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-ink-400 hover:text-ink-700"
                >
                  <X size={15} />
                </button>
              ) : null}
            </div>

            {!rows.length ? (
              <EmptyState
                icon={Search}
                title="No matches"
                message={`Nothing matched "${query}".`}
              />
            ) : (
              <Table
                head={[
                  { label: "Store" },
                  { label: "Area" },
                  { label: "Platform" },
                  { label: "Location" },
                  { label: "Opening cost", align: "right" },
                  { label: "Capacity", align: "right" },
                  { label: "Status" },
                ]}
              >
                {rows.map((s) => (
                  <Row
                    key={s.id}
                    onClick={() => setSelected(s)}
                    active={selected?.id === s.id}
                  >
                    <td className="pr-3 font-medium text-ink-800">{text(s.name)}</td>
                    <td className="pr-3 text-ink-600">{text(s.area)}</td>
                    <td className="pr-3 text-ink-600">{text(s.platform)}</td>
                    <td className="tnum pr-3 text-[12px] text-ink-500">
                      {s.latitude}, {s.longitude}
                    </td>
                    <td className="tnum pr-3 text-right text-ink-600">
                      {money(s.opening_cost, 0)}
                    </td>
                    <td className="tnum pr-3 text-right text-ink-600">
                      {num(s.storage_capacity)}
                    </td>
                    <td>
                      {s.is_candidate ? (
                        <Badge tone="success">Candidate</Badge>
                      ) : (
                        <Badge tone="neutral">Not candidate</Badge>
                      )}
                    </td>
                  </Row>
                ))}
              </Table>
            )}
          </>
        )}
      </Card>

      {selected ? (
        <Card>
          <SectionTitle
            icon={StoreIcon}
            title={selected.name}
            subtitle={`Store #${selected.id}`}
            right={
              <button
                onClick={() => setSelected(null)}
                className="text-ink-400 hover:text-ink-700"
                aria-label="Close detail"
              >
                <X size={17} />
              </button>
            }
          />
          <div className="grid gap-x-8 gap-y-2.5 text-[13px] sm:grid-cols-2 lg:grid-cols-3">
            {Object.entries(selected).map(([k, v]) => (
              <div
                key={k}
                className="flex justify-between gap-3 border-b border-ink-100 pb-2"
              >
                <span className="text-ink-400">{k}</span>
                <span className="tnum text-right font-medium text-ink-700">
                  {typeof v === "boolean" ? (v ? "true" : "false") : text(v)}
                </span>
              </div>
            ))}
          </div>
          <p className="mt-4 text-[11.5px] leading-relaxed text-ink-400">
            <strong className="font-semibold">data_source</strong> records where
            each row&apos;s numbers came from. Coordinates marked
            APPROX_AREA_CENTROID are approximate area centres, not surveyed
            addresses; values marked DEMO_ASSUMPTION are illustrative.
          </p>
        </Card>
      ) : null}
    </div>
  );
}
