import {
  Lightbulb, Wind, Droplets, Trash2, Flame, Users, CircleHelp,
  CircleDot, Clock3, CircleCheckBig,
} from "lucide-react";

export const CATEGORIES = ["streetlight", "pollution", "water", "waste", "energy", "crowd_monitoring", "other"];
export const URGENCIES = ["low", "medium", "high"];
export const STATUSES = ["open", "in_progress", "resolved"];

export const CATEGORY_META = {
  streetlight: { label: "Streetlight", icon: Lightbulb, color: "#f5a623" },
  pollution: { label: "Pollution", icon: Wind, color: "#8b5cf6" },
  water: { label: "Water", icon: Droplets, color: "#3b82f6" },
  waste: { label: "Waste", icon: Trash2, color: "#10b981" },
  energy: { label: "Energy", icon: Flame, color: "#ef4444" },
  crowd_monitoring: { label: "Crowd Monitoring", icon: Users, color: "#ec4899" },
  other: { label: "Other", icon: CircleHelp, color: "#64748b" },
};

export const STATUS_META = {
  open: { label: "Open", icon: CircleDot, color: "#3b82f6" },
  in_progress: { label: "In Progress", icon: Clock3, color: "#f5a623" },
  resolved: { label: "Resolved", icon: CircleCheckBig, color: "#30a46c" },
};

export const URGENCY_COLORS = { high: "#e5484d", medium: "#f5a623", low: "#30a46c" };

export const categoryLabel = (c) => CATEGORY_META[c]?.label ?? c;
export const statusLabel = (s) => STATUS_META[s]?.label ?? s;
export const urgencyLabel = (u) => (u ? u[0].toUpperCase() + u.slice(1) : u);

export function formatDate(iso, withTime = false) {
  const d = new Date(iso);
  return withTime
    ? d.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" })
    : d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}
