import { CATEGORY_META, STATUS_META, categoryLabel, statusLabel, urgencyLabel } from "../constants.js";

export function CategoryBadge({ category }) {
  const Icon = CATEGORY_META[category]?.icon;
  return (
    <span className="badge category">
      {Icon && <Icon size={13} aria-hidden="true" />}
      {categoryLabel(category)}
    </span>
  );
}

export function UrgencyBadge({ urgency, suffix = "" }) {
  return <span className={`badge ${urgency}`}>{urgencyLabel(urgency)}{suffix}</span>;
}

export function StatusBadge({ status }) {
  const Icon = STATUS_META[status]?.icon;
  return (
    <span className={`badge ${status}`}>
      {Icon && <Icon size={13} aria-hidden="true" />}
      {statusLabel(status)}
    </span>
  );
}
