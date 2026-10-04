import { useMemo } from "react";
import {
  MapContainer,
  TileLayer,
  CircleMarker,
  Popup,
  Polyline,
  Tooltip,
} from "react-leaflet";
import { MapPin } from "lucide-react";
import { Badge, Card, Note, SectionTitle } from "./Primitives";
import EmptyState from "./EmptyState";
import { areaCentroidFromStores, isNum, minutes, text } from "../utils/formatters";

/**
 * Store markers use the latitude/longitude returned by /api/stores. Nothing is
 * invented.
 *
 * /api/demand returns NO coordinates, so demand areas cannot be placed from
 * that endpoint. Where an area name matches a candidate store's `area`, we
 * place the area at the centroid of those stores -- the same approximation the
 * backend itself uses to compute delivery times (documented in
 * app/services/data_service.py). Those markers are drawn as dashed rings and
 * labelled "approximate" so they are never mistaken for surveyed points. Areas
 * with no matching store get no marker at all.
 */
export default function MapView({ stores, result, demandAreas }) {
  const located = useMemo(
    () => (stores || []).filter((s) => isNum(s.latitude) && isNum(s.longitude)),
    [stores],
  );

  const selectedIds = useMemo(
    () => new Set(result?.selected_stores || []),
    [result],
  );

  const assignments = useMemo(
    () => (result?.area_assignments || []).filter((a) => a.served),
    [result],
  );

  // Area centroids, derived as described above. Only for areas we can locate.
  const areaPoints = useMemo(() => {
    const names = new Set([
      ...(demandAreas || []),
      ...(result?.area_assignments || []).map((a) => a.area),
    ]);
    const out = [];
    for (const name of names) {
      const c = areaCentroidFromStores(name, located);
      if (c) out.push({ name, ...c });
    }
    return out;
  }, [demandAreas, result, located]);

  const lines = useMemo(() => {
    if (!assignments.length) return [];
    const byId = new Map(located.map((s) => [s.id, s]));
    const byArea = new Map(areaPoints.map((a) => [a.name, a]));
    const out = [];
    for (const a of assignments) {
      const store = byId.get(a.store_id);
      const area = byArea.get(a.area);
      if (store && area) {
        out.push({
          key: `${a.area}-${a.store_id}`,
          positions: [
            [area.lat, area.lng],
            [store.latitude, store.longitude],
          ],
          label: `${a.area} → ${a.store_name} · ${minutes(a.delivery_time_min)}`,
        });
      }
    }
    return out;
  }, [assignments, located, areaPoints]);

  const center = useMemo(() => {
    if (!located.length) return [11.9416, 79.8083];
    return [
      located.reduce((a, s) => a + s.latitude, 0) / located.length,
      located.reduce((a, s) => a + s.longitude, 0) / located.length,
    ];
  }, [located]);

  if (!located.length) {
    return (
      <Card>
        <SectionTitle
          icon={MapPin}
          title="Store Network Map"
          subtitle="Candidate dark stores"
        />
        <EmptyState
          icon={MapPin}
          title="No store coordinates available"
          message="The backend returned no stores with latitude and longitude, so no map can be drawn. Coordinates are never invented here."
        />
      </Card>
    );
  }

  return (
    <Card padded={false}>
      <div className="p-5 pb-3">
        <SectionTitle
          icon={MapPin}
          title="Store Network Map"
          subtitle={`${located.length} candidate store${
            located.length === 1 ? "" : "s"
          }${selectedIds.size ? ` · ${selectedIds.size} selected` : ""}`}
          right={
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="success">Selected</Badge>
              <Badge tone="neutral">Candidate</Badge>
              <Badge tone="violet">Demand area (approx.)</Badge>
            </div>
          }
        />
      </div>

      <div className="h-[420px] w-full overflow-hidden border-y border-ink-200">
        <MapContainer
          center={center}
          zoom={13}
          scrollWheelZoom={false}
          style={{ height: "100%", width: "100%" }}
        >
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />

          {/* Assignment lines: only drawn when BOTH endpoints have a location. */}
          {lines.map((l) => (
            <Polyline
              key={l.key}
              positions={l.positions}
              pathOptions={{
                color: "#2049dd",
                weight: 2,
                opacity: 0.55,
                dashArray: "6 5",
              }}
            >
              <Tooltip sticky>{l.label}</Tooltip>
            </Polyline>
          ))}

          {/* Demand areas: dashed ring, explicitly approximate. */}
          {areaPoints.map((a) => (
            <CircleMarker
              key={`area-${a.name}`}
              center={[a.lat, a.lng]}
              radius={13}
              pathOptions={{
                color: "#7c3aed",
                weight: 1.5,
                dashArray: "3 3",
                fillColor: "#7c3aed",
                fillOpacity: 0.07,
              }}
            >
              <Popup>
                <div className="space-y-0.5">
                  <div className="text-[13px] font-semibold">{a.name}</div>
                  <div className="text-ink-500">Demand area</div>
                  <div className="mt-1 text-[11px] text-ink-400">
                    Approximate location: centroid of {a.derivedFrom} store
                    {a.derivedFrom === 1 ? "" : "s"} in this area. The demand API
                    returns no coordinates.
                  </div>
                </div>
              </Popup>
            </CircleMarker>
          ))}

          {/* Candidate stores: real coordinates from /api/stores. */}
          {located.map((s) => {
            const chosen = selectedIds.has(s.id);
            return (
              <CircleMarker
                key={`store-${s.id}`}
                center={[s.latitude, s.longitude]}
                radius={chosen ? 11 : 7}
                pathOptions={{
                  color: chosen ? "#047857" : "#64748b",
                  weight: chosen ? 3 : 1.5,
                  fillColor: chosen ? "#10b981" : "#94a3b8",
                  fillOpacity: chosen ? 0.9 : 0.55,
                }}
              >
                <Popup>
                  <div className="space-y-1">
                    <div className="text-[13px] font-semibold">{s.name}</div>
                    <dl className="grid grid-cols-[auto_1fr] gap-x-2 text-[12px]">
                      <dt className="text-ink-400">Area</dt>
                      <dd>{text(s.area)}</dd>
                      <dt className="text-ink-400">Platform</dt>
                      <dd>{text(s.platform)}</dd>
                      <dt className="text-ink-400">Latitude</dt>
                      <dd className="tnum">{s.latitude}</dd>
                      <dt className="text-ink-400">Longitude</dt>
                      <dd className="tnum">{s.longitude}</dd>
                      <dt className="text-ink-400">Candidate</dt>
                      <dd>{s.is_candidate ? "Yes" : "No"}</dd>
                      <dt className="text-ink-400">Selected</dt>
                      <dd className={chosen ? "font-semibold text-emerald-700" : ""}>
                        {result ? (chosen ? "Yes" : "No") : "No run yet"}
                      </dd>
                    </dl>
                  </div>
                </Popup>
              </CircleMarker>
            );
          })}
        </MapContainer>
      </div>

      <div className="space-y-2 p-5 pt-3">
        <Note tone="info">
          Store markers use the coordinates returned by{" "}
          <code className="font-mono text-[11px]">/api/stores</code>. The demand
          endpoint returns no coordinates, so demand areas are drawn at the
          centroid of the stores sharing each area name — the same approximation
          the solver uses for delivery times. They are marked approximate, and
          any area without a matching store is omitted rather than guessed.
        </Note>
        {result && !lines.length && assignments.length ? (
          <Note tone="warning">
            Assignments exist but no lines could be drawn, because the areas
            involved have no locatable coordinates. See the assignments table
            below.
          </Note>
        ) : null}
      </div>
    </Card>
  );
}
