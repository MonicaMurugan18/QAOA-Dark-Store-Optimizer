import { useMemo } from "react";
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
import { BarChart3 } from "lucide-react";
import { Badge, Card, Note, Row, SectionTitle, Table } from "../components/Primitives";
import LoadingState from "../components/LoadingState";
import ErrorState from "../components/ErrorState";
import EmptyState from "../components/EmptyState";
import { useDemand, useProducts } from "../hooks/useOptimization";
import { minutes, num, text } from "../utils/formatters";

const COLORS = ["#3465f0", "#0d9488", "#7c3aed", "#d97706", "#db2777", "#0891b2"];

export default function Demand() {
  const demand = useDemand();
  const products = useProducts();

  const productName = useMemo(() => {
    const map = new Map((products.data || []).map((p) => [p.id, p.name]));
    return (id) => map.get(id) || `Product #${id}`;
  }, [products.data]);

  const grouped = useMemo(() => {
    const byArea = new Map();
    for (const d of demand.data || []) {
      if (!byArea.has(d.area)) byArea.set(d.area, []);
      byArea.get(d.area).push(d);
    }
    return byArea;
  }, [demand.data]);

  const { chartData, series } = useMemo(() => {
    const names = new Set();
    const rows = [];
    for (const [area, items] of grouped.entries()) {
      const row = { area };
      for (const it of items) {
        const n = productName(it.product_id);
        names.add(n);
        row[n] = (row[n] || 0) + it.demand_quantity;
      }
      rows.push(row);
    }
    return { chartData: rows, series: Array.from(names) };
  }, [grouped, productName]);

  const status = demand.status;

  return (
    <div className="space-y-6">
      <Card>
        <SectionTitle
          icon={BarChart3}
          title="Demand by Area"
          subtitle="Fields as returned by GET /api/demand"
          right={
            status === "ok" ? (
              <Badge tone="info">
                {grouped.size} areas · {(demand.data || []).length} rows
              </Badge>
            ) : null
          }
        />

        {status === "loading" ? (
          <LoadingState label="Loading demand..." rows={5} />
        ) : status === "error" ? (
          <ErrorState error={demand.error} onRetry={demand.refresh} />
        ) : !(demand.data || []).length ? (
          <EmptyState
            icon={BarChart3}
            title="No demand rows found"
            message="The backend returned no demand. Load the seed data first."
          />
        ) : (
          <>
            <div className="mb-5">
              <Note tone="info">
                The demand endpoint returns no latitude or longitude, so demand
                areas are listed here rather than placed on the map from invented
                coordinates.
              </Note>
            </div>

            <div className="mb-6 h-72">
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
                    dataKey="area"
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
                    formatter={(v, n) => [`${num(v)} units`, n]}
                    contentStyle={{
                      fontSize: 12,
                      borderRadius: 8,
                      border: "1px solid #dde1e9",
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11.5, paddingTop: 6 }} />
                  {series.map((s, i) => (
                    <Bar
                      key={s}
                      dataKey={s}
                      stackId="a"
                      fill={COLORS[i % COLORS.length]}
                      maxBarSize={64}
                    />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="space-y-5">
              {Array.from(grouped.entries()).map(([area, items]) => {
                const total = items.reduce(
                  (a, i) => a + (i.demand_quantity || 0),
                  0,
                );
                return (
                  <div key={area}>
                    <div className="mb-2 flex items-baseline justify-between gap-3">
                      <h3 className="text-[13.5px] font-semibold text-ink-900">
                        {area}
                      </h3>
                      <span className="tnum text-[12px] text-ink-500">
                        {num(total)} units
                      </span>
                    </div>
                    <Table
                      head={[
                        { label: "Product" },
                        { label: "Quantity", align: "right" },
                        { label: "Delivery limit", align: "right" },
                        { label: "Data source" },
                      ]}
                    >
                      {items.map((d) => (
                        <Row key={d.id}>
                          <td className="pr-3 text-ink-700">
                            {productName(d.product_id)}
                          </td>
                          <td className="tnum pr-3 text-right text-ink-600">
                            {num(d.demand_quantity)}
                          </td>
                          <td className="tnum pr-3 text-right text-ink-600">
                            {minutes(d.delivery_time_limit)}
                          </td>
                          <td className="text-[11.5px] text-ink-400">
                            {text(d.data_source)}
                          </td>
                        </Row>
                      ))}
                    </Table>
                  </div>
                );
              })}
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
