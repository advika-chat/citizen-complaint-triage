import { ArrowDown, ArrowUp, ArrowUpDown, Copy, Image as ImageIcon } from "lucide-react";
import { STATUSES, formatDate, statusLabel } from "../constants.js";
import { CategoryBadge, UrgencyBadge } from "./Badges.jsx";

const SORTABLE = { created_at: "Submitted", category: "Category", urgency: "Urgency", status: "Status" };

function SortHeader({ field, sort, order, onSort }) {
  const Icon = sort !== field ? ArrowUpDown : order === "asc" ? ArrowUp : ArrowDown;
  return (
    <th
      className="sortable" onClick={() => onSort(field)}
      aria-sort={sort === field ? (order === "asc" ? "ascending" : "descending") : "none"}
    >
      <span>{SORTABLE[field]} <Icon size={13} aria-hidden="true" /></span>
    </th>
  );
}

export default function ComplaintTable({
  items, loading, selected, onToggle, onToggleAll, sort, order, onSort, onOpen, onStatusChange, showSimilarity,
}) {
  const allSelected = items.length > 0 && items.every((c) => selected.has(c.id));
  const sortProps = { sort, order, onSort };
  const cols = showSimilarity ? 8 : 7;

  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th style={{ width: 36 }}>
              <input type="checkbox" aria-label="Select all on this page" checked={allSelected} onChange={onToggleAll} />
            </th>
            <SortHeader field="created_at" {...sortProps} />
            <th>Summary</th>
            <SortHeader field="category" {...sortProps} />
            <SortHeader field="urgency" {...sortProps} />
            <th>Department</th>
            <SortHeader field="status" {...sortProps} />
            {showSimilarity && <th>Match</th>}
          </tr>
        </thead>
        <tbody>
          {loading &&
            Array.from({ length: 5 }).map((_, i) => (
              <tr key={`sk${i}`}>
                <td colSpan={cols}><div className="skeleton skeleton-row" /></td>
              </tr>
            ))}
          {!loading && items.length === 0 && (
            <tr><td colSpan={cols} className="empty">No complaints match the current filters.</td></tr>
          )}
          {!loading &&
            items.map((c) => (
              <tr key={c.id} onClick={() => onOpen(c.id)}>
                <td onClick={(e) => e.stopPropagation()}>
                  <input
                    type="checkbox" aria-label={`Select ${c.summary}`}
                    checked={selected.has(c.id)} onChange={() => onToggle(c.id)}
                  />
                </td>
                <td>{formatDate(c.created_at)}</td>
                <td className="summary-cell">
                  {c.photo_url && <ImageIcon size={14} aria-label="Has photo" style={{ marginRight: 6, verticalAlign: "-2px" }} />}
                  {c.summary}{" "}
                  {c.duplicate_of && <span className="badge dup"><Copy size={11} aria-hidden="true" /> duplicate</span>}
                </td>
                <td><CategoryBadge category={c.category} /></td>
                <td><UrgencyBadge urgency={c.urgency} /></td>
                <td>{c.suggested_department}</td>
                <td onClick={(e) => e.stopPropagation()}>
                  <select
                    aria-label={`Status of ${c.summary}`} value={c.status}
                    onChange={(e) => onStatusChange(c, e.target.value)}
                  >
                    {STATUSES.map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
                  </select>
                </td>
                {showSimilarity && <td>{c.similarity != null ? `${Math.round(c.similarity * 100)}%` : ""}</td>}
              </tr>
            ))}
        </tbody>
      </table>
    </div>
  );
}
