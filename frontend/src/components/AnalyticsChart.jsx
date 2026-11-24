import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { CATEGORY_META } from "../constants.js";

export default function AnalyticsChart({ byCategory }) {
  const data = Object.entries(byCategory || {}).map(([key, count]) => ({
    key, name: CATEGORY_META[key]?.label ?? key, count,
  }));
  return (
    <ResponsiveContainer width="100%" height={260}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -20, bottom: 24 }}>
        <CartesianGrid strokeDasharray="3 3" vertical={false} />
        <XAxis dataKey="name" angle={-35} textAnchor="end" interval={0} height={60} tick={{ fontSize: 11 }} />
        <YAxis allowDecimals={false} tick={{ fontSize: 11 }} />
        <Tooltip />
        <Bar dataKey="count" radius={[6, 6, 0, 0]}>
          {data.map((d) => <Cell key={d.key} fill={CATEGORY_META[d.key]?.color ?? "#64748b"} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
