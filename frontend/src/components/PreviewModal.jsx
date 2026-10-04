import { X, Cpu, CircleCheck, CircleAlert } from "lucide-react";
import { Badge, Button, Note, Table, Row } from "./Primitives";
import LoadingState from "./LoadingState";
import ErrorState from "./ErrorState";
import { num, minutes } from "../utils/formatters";

/**
 * QUBO preview modal. Explains the quantum formulation size to a technical
 * audience using the real numbers from POST /api/optimization/preview.
 */
export default function PreviewModal({ open, onClose, data, loading, error }) {
  if (!open) return null;

  const q = data?.qubo_compact;
  const inst = data?.instance;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-ink-950/60 p-4 sm:p-8">
      <div className="w-full max-w-3xl rounded-lg border border-ink-200 bg-white shadow-xl">
        <div className="flex items-start justify-between gap-4 border-b border-ink-200 px-5 py-4">
          <div className="flex items-start gap-3">
            <span className="mt-0.5 flex h-8 w-8 items-center justify-center rounded-md bg-violet-50 text-violet-600">
              <Cpu size={17} />
            </span>
            <div>
              <h2 className="text-[15px] font-semibold text-ink-900">
                QUBO Preview
              </h2>
              <p className="text-[12.5px] text-ink-500">
                Problem size for this instance, before any circuit is run
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-ink-400 hover:bg-ink-100 hover:text-ink-700"
            aria-label="Close"
          >
            <X size={18} />
          </button>
        </div>

        <div className="max-h-[70vh] overflow-y-auto px-5 py-5">
          {loading ? (
            <LoadingState label="Building the QUBO..." rows={3} />
          ) : error ? (
            <ErrorState error={error} />
          ) : !data ? (
            <p className="text-[13px] text-ink-500">No preview data.</p>
          ) : (
            <div className="space-y-5">
              <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                {[
                  ["Decision Variables", q?.n_decision_variables],
                  ["Auxiliary Variables", q?.n_auxiliary_variables],
                  ["Total Qubits", q?.n_qubits],
                  ["Feasible Links", inst?.service_feasible_links],
                ].map(([label, value]) => (
                  <div
                    key={label}
                    className="rounded-md border border-ink-200 bg-ink-50/60 p-3.5"
                  >
                    <div className="text-[11px] font-medium uppercase tracking-wide text-ink-400">
                      {label}
                    </div>
                    <div className="tnum mt-1 text-[22px] font-semibold text-ink-900">
                      {num(value)}
                    </div>
                  </div>
                ))}
              </div>

              <div className="flex flex-wrap items-center gap-2">
                {q?.within_simulator_limit ? (
                  <Badge tone="success">
                    <CircleCheck size={12} /> Within simulator limit (
                    {num(q.simulator_limit)} qubits)
                  </Badge>
                ) : (
                  <Badge tone="danger">
                    <CircleAlert size={12} /> Exceeds simulator limit (
                    {num(q?.simulator_limit)} qubits)
                  </Badge>
                )}
                {q?.encoding ? (
                  <Badge tone="violet">encoding: {q.encoding}</Badge>
                ) : null}
                {q?.search_space_size ? (
                  <Badge tone="neutral">
                    search space {q.search_space_size}
                  </Badge>
                ) : null}
              </div>

              <div className="grid gap-x-6 gap-y-2 rounded-md border border-ink-200 p-4 text-[12.5px] sm:grid-cols-2">
                {[
                  ["Candidate stores", inst?.stores],
                  ["Demand areas", inst?.areas],
                  ["Products", inst?.products],
                  ["Total demand units", inst?.total_demand_units],
                  ["Total demand volume", inst?.total_demand_volume],
                  ["Total capacity", inst?.total_capacity],
                  ["Constraints in model", q?.constraints_in_reference_model],
                  ["Penalty weight", q?.penalty_weight],
                ]
                  .filter(([, v]) => v !== undefined && v !== null)
                  .map(([label, v]) => (
                    <div key={label} className="flex justify-between gap-3">
                      <span className="text-ink-400">{label}</span>
                      <span className="tnum font-medium text-ink-700">
                        {typeof v === "number" ? num(v, v % 1 ? 2 : 0) : String(v)}
                      </span>
                    </div>
                  ))}
              </div>

              {data?.store_area_links?.length ? (
                <div>
                  <div className="mb-2 text-[12.5px] font-semibold text-ink-700">
                    Store → area links
                  </div>
                  <Table
                    head={[
                      { label: "Store" },
                      { label: "Area" },
                      { label: "Distance", align: "right" },
                      { label: "Delivery", align: "right" },
                      { label: "Within limit" },
                    ]}
                  >
                    {data.store_area_links.map((l, i) => (
                      <Row key={i}>
                        <td className="pr-3 text-ink-700">{l.store_name}</td>
                        <td className="pr-3 text-ink-600">{l.area}</td>
                        <td className="tnum pr-3 text-right text-ink-600">
                          {num(l.road_distance_km, 2)} km
                        </td>
                        <td className="tnum pr-3 text-right text-ink-600">
                          {minutes(l.delivery_time_min)}
                        </td>
                        <td>
                          {l.within_service_limit ? (
                            <Badge tone="success">Yes</Badge>
                          ) : (
                            <Badge tone="neutral">No</Badge>
                          )}
                        </td>
                      </Row>
                    ))}
                  </Table>
                  <p className="mt-2 text-[11.5px] text-ink-400">
                    Links outside the delivery limit are never created as
                    variables, which is how the service constraint is enforced
                    without spending qubits.
                  </p>
                </div>
              ) : null}

              {data?.warnings?.length ? (
                <Note tone="warning">
                  <ul className="list-disc space-y-1 pl-4">
                    {data.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </Note>
              ) : null}

              {q?.notes?.length ? (
                <ul className="space-y-1.5 border-t border-ink-100 pt-4 text-[12px] leading-relaxed text-ink-500">
                  {q.notes.map((n, i) => (
                    <li key={i} className="flex gap-2">
                      <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-ink-300" />
                      {n}
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          )}
        </div>

        <div className="flex justify-end border-t border-ink-200 px-5 py-3.5">
          <Button variant="secondary" onClick={onClose}>
            Close
          </Button>
        </div>
      </div>
    </div>
  );
}
