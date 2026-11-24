export default function StatTile({ icon: Icon, label, value, color, soft }) {
  return (
    <div className="stat-tile">
      <div className="stat-icon" style={{ background: soft, color }}>
        <Icon size={22} aria-hidden="true" />
      </div>
      <div>
        <div className="stat-value">{value ?? "-"}</div>
        <div className="stat-label">{label}</div>
      </div>
    </div>
  );
}
