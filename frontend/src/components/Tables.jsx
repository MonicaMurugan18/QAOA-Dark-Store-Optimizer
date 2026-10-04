/**
 * Result tables: selected stores, area assignments, inventory allocation.
 * Any field the API does not provide is rendered as a dash, never invented.
 */
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Legend,
  Tooltip as RTooltip,
  ResponsiveContainer,
} from "recharts";
import { Store, Route, Boxes, CheckCircle2, MinusCircle } from "lucide-react";
import { Badge, Card, Row, SectionTitle, Table } from "./Primitives";
import EmptyState from "./EmptyState";
import { minutes, money, num, text } from "../utils/formatters";

const SERIES_COLORS = ["#3465f0", "#0d9488", "#7c3aed", "#d97706", "#db2777", "#0891b2"];

/* ------------------------------------------------------------ selected stores */
export function SelectedStores({ result, stores }) {
  const ids = result?.selected_stores || [];
  const byId = new Map((stores || []).map((s) => [s.id, s]));

  return (
    <Card>
      <SectionTitle
        icon={Store}
        title="Selected Stores"
        subtitle="Dark stores the solver recommends opening"
        right={<Badge tone="success">{ids.length} selected</Badge>}
      />
      {ids.length === 0 ? (
        <EmptyState
          icon={Store}
          title="No stores selected"
          message="The solution opens no store. With this budget and these constraints, serving demand did not pay for itself."
        />
      ) : (
        <Table
          head={[
            { label: "Store" },
            { label: "Area" },
            { label: "Platform" },
            { label: "Opening cost", align: "right" },
            { label: "Capacity", align: "right" },
            { label: "Status" },
          ]}
        >
          {ids.map((id, i) => {
            const s = byId.get(id);
            const name =
              s?.name || result?.selected_store_names?.[i] || `Store #${id}`;
            return (
              <Row key={id}>
                <td className="pr-3 font-medium text-ink-800">{name}</td>
                <td className="pr-3 text-ink-600">{text(s?.area)}</td>
                <td className="pr-3 text-ink-600">{text(s?.platform)}</td>
                <td className="tnum pr-3 text-right text-ink-600">
                  {s ? money(s.opening_cost, 0) : "—"}
                </td>
                <td className="tnum pr-3 text-right text-ink-600">
                  {s ? num(s.storage_capacity) : "—"}
                </td>
                <td>
                  <Badge tone="success">
                    <CheckCircle2 size={12} /> Selected
                  </Badge>
                </td>
              </Row>
            );
          })}
        </Table>
      )}
    </Card>
  );
}

/* --------------------------------------------------------- area assignments */
export function AssignmentTable({ result }) {
  const rows = result?.area_assignments || [];
  const servedCount = rows.filter((r) => r.served).length;

  return (
    <Card>
      <SectionTitle
        icon={Route}
        title="Customer / Demand Assignments"
        subtitle="Which store serves each demand area"
        right={
          <Badge tone={servedCount === rows.length ? "success" : "warning"}>
            {servedCount} / {rows.length} served
          </Badge>
        }
      />
      {rows.length === 0 ? (
        <EmptyState
          icon={Route}
          title="No assignments returned"
          message="The result contains no area assignments."
        />
      ) : (
        <Table
          head={[
            { label: "Demand Area" },
            { label: "Assigned Store" },
            { label: "Delivery", align: "right" },
            { label: "Status" },
          ]}
        >
          {rows.map((r) => (
            <Row key={r.area}>
              <td className="pr-3 font-medium text-ink-800">{text(r.area)}</td>
              <td className="pr-3 text-ink-600">
                {r.store_name ? (
                  text(r.store_name)
                ) : (
                  <span className="text-ink-400">Not assigned</span>
                )}
              </td>
              <td className="tnum pr-3 text-right text-ink-600">
                {typeof r.delivery_time_min === "number"
                  ? minutes(r.delivery_time_min)
                  : "—"}
              </td>
              <td>
                {r.served ? (
                  <Badge tone="success">
                    <CheckCircle2 size={12} /> Served
                  </Badge>
                ) : (
                  <Badge tone="warning">
                    <MinusCircle size={12} /> Unserved
                  </Badge>
                )}
              </td>
            </Row>
          ))}
        </Table>
      )}
      <p className="mt-3 text-[11.5px] leading-relaxed text-ink-400">
        Leaving an area unserved is permitted by the model: it forfeits that
        area&apos;s margin rather than breaking a constraint. Demand quantity per
        area is on the Demand page; the result payload reports totals, not
        per-area demand.
      </p>
    </Card>
  );
}

/* ------------------------------------------------------ inventory allocation */
export function InventoryTable({ result }) {
  const rows = result?.inventory_allocation || [];

  // Group by store for the per-store listing.
  const byStore = new Map();
  for (const r of rows) {
    if (!byStore.has(r.store_name)) byStore.set(r.store_name, []);
    byStore.get(r.store_name).push(r);
  }

  // Chart: one bar group per store, one series per product.
  const products = Array.from(new Set(rows.map((r) => r.product_name)));
  const chartData = Array.from(byStore.entries()).map(([store, items]) => {
    const row = { store };
    for (const it of items) row[it.product_name] = it.quantity;
    return row;
  });

  const totalUnits = rows.reduce((a, r) => a + (r.quantity || 0), 0);

  return (
    <Card>
      <SectionTitle
        icon={Boxes}
        title="Inventory Allocation"
        subtitle="Units of each product to stock in each opened store"
        right={
          rows.length ? (
            <Badge tone="info">{num(totalUnits)} units total</Badge>
          ) : null
        }
      />

      {rows.length === 0 ? (
        <EmptyState
          icon={Boxes}
          title="No inventory allocated"
          message="No store was opened, so no inventory is assigned."
        />
      ) : (
        <>
          <div className="space-y-5">
            {Array.from(byStore.entries()).map(([store, items]) => {
              const storeTotal = items.reduce((a, i) => a + i.quantity, 0);
              return (
                <div
                  key={store}
                  className="rounded-md border border-ink-200 bg-ink-50/50 p-4"
                >
                  <div className="mb-3 flex items-baseline justify-between gap-3">
                    <div className="text-[13.5px] font-semibold text-ink-900">
                      {store}
                    </div>
                    <div className="tnum text-[12px] text-ink-500">
                      {num(storeTotal)} units
                    </div>
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {items.map((it) => (
                      <div
                        key={`${it.store_id}-${it.product_id}`}
                        className="flex items-baseline justify-between gap-2 rounded border border-ink-200 bg-white px-3 py-2"
                      >
                        <span className="truncate text-[12.5px] text-ink-600">
                          {text(it.product_name)}
                        </span>
                        <span className="tnum shrink-0 text-[14px] font-semibold text-ink-900">
                          {num(it.quantity)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="mt-6">
            <div className="mb-2 text-[12.5px] font-semibold text-ink-700">
              Inventory by store and product
            </div>
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={chartData}
                  margin={{ top: 4, right: 8, bottom: 4, left: 0 }}
                >
                  <CartesianGrid
                    strokeDasharray="3 3"
                    stroke="#eef0f4"
                    vertical={false}
                  />
                  <XAxis
                    dataKey="store"
                    tick={{ fontSize: 11.5, fill: "#5f6b82" }}
                    axisLine={{ stroke: "#dde1e9" }}
                    tickLine={false}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: "#8d97ab" }}
                    axisLine={false}
                    tickLine={false}
                    width={48}
                  />
                  <RTooltip
                    formatter={(v, n) => [num(v) + " units", n]}
                    contentStyle={{
                      fontSize: 12,
                      borderRadius: 8,
                      border: "1px solid #dde1e9",
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11.5, paddingTop: 6 }} />
                  {products.map((p, i) => (
                    <Bar
                      key={p}
                      dataKey={p}
                      fill={SERIES_COLORS[i % SERIES_COLORS.length]}
                      radius={[3, 3, 0, 0]}
                      maxBarSize={48}
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>

          <p className="mt-3 text-[11.5px] leading-relaxed text-ink-400">
            Inventory is derived from the assignment: a store stocks exactly what
            its assigned areas demand. It is reported by the backend, not
            computed here.
          </p>
        </>
      )}
    </Card>
  );
}
