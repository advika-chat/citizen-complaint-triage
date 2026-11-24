import { CircleMarker, MapContainer, Popup, TileLayer } from "react-leaflet";
import { URGENCY_COLORS, categoryLabel, statusLabel } from "../constants.js";

const AUSTIN = [30.2672, -97.7431];

export default function ComplaintMap({ items }) {
  const located = items.filter((c) => c.latitude != null && c.longitude != null);
  const center = located.length ? [located[0].latitude, located[0].longitude] : AUSTIN;
  return (
    <>
      <div className="map-box">
        <MapContainer center={center} zoom={14} style={{ height: "100%", width: "100%" }} scrollWheelZoom={false}>
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          {located.map((c) => (
            <CircleMarker
              key={c.id}
              center={[c.latitude, c.longitude]}
              radius={9}
              pathOptions={{ color: "#fff", weight: 2, fillColor: URGENCY_COLORS[c.urgency], fillOpacity: 0.9 }}
            >
              <Popup>
                <strong>{c.summary}</strong>
                <br />
                {categoryLabel(c.category)} - {statusLabel(c.status)}
              </Popup>
            </CircleMarker>
          ))}
        </MapContainer>
      </div>
      <div className="legend">
        {["high", "medium", "low"].map((u) => (
          <span key={u}>
            <span className="dot" style={{ background: URGENCY_COLORS[u] }} />
            {u[0].toUpperCase() + u.slice(1)} urgency
          </span>
        ))}
        <span style={{ marginLeft: "auto" }}>{located.length} pinned</span>
      </div>
    </>
  );
}
