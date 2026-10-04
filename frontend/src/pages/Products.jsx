import { Package } from "lucide-react";
import { Badge, Card, Row, SectionTitle, Table } from "../components/Primitives";
import LoadingState from "../components/LoadingState";
import ErrorState from "../components/ErrorState";
import EmptyState from "../components/EmptyState";
import { useProducts } from "../hooks/useOptimization";
import { money, num, text } from "../utils/formatters";

export default function Products() {
  const { data, status, error, refresh } = useProducts();

  return (
    <Card>
      <SectionTitle
        icon={Package}
        title="Product Catalogue"
        subtitle="Fields as returned by GET /api/products"
        right={
          status === "ok" ? (
            <Badge tone="info">{(data || []).length} products</Badge>
          ) : null
        }
      />

      {status === "loading" ? (
        <LoadingState label="Loading products..." rows={5} />
      ) : status === "error" ? (
        <ErrorState error={error} onRetry={refresh} />
      ) : !(data || []).length ? (
        <EmptyState
          icon={Package}
          title="No products found"
          message="The backend returned no products. Load the seed data first."
        />
      ) : (
        <>
          <Table
            head={[
              { label: "Product" },
              { label: "Category" },
              { label: "Unit volume", align: "right" },
              { label: "Unit cost", align: "right" },
              { label: "Data source" },
            ]}
          >
            {data.map((p) => (
              <Row key={p.id}>
                <td className="pr-3 font-medium text-ink-800">{text(p.name)}</td>
                <td className="pr-3 text-ink-600">{text(p.category)}</td>
                <td className="tnum pr-3 text-right text-ink-600">
                  {num(p.unit_volume, 2)}
                </td>
                <td className="tnum pr-3 text-right text-ink-600">
                  {money(p.unit_cost, 0)}
                </td>
                <td className="text-[11.5px] text-ink-400">
                  {text(p.data_source)}
                </td>
              </Row>
            ))}
          </Table>
          <p className="mt-3 text-[11.5px] leading-relaxed text-ink-400">
            <strong className="font-semibold">Unit volume</strong> is the shelf
            space one unit consumes, in the same units as a store&apos;s storage
            capacity. That is how one capacity number can bound a mixed basket.
          </p>
        </>
      )}
    </Card>
  );
}
