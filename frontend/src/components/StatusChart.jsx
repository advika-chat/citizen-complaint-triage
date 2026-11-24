import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import { STATUS_META } from "../constants.js";

export default function StatusChart({ byStatus }) {
  const data = Object.entries(byStatus || {}).map(([key, value]) => ({
    key, name: STATUS_META[key]?.label ?? key, value,
  }));
  return (
    <ResponsiveContainer width="100%" height={260}>
      <PieChart>
        <Pie data={data} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={2}>
          {data.map((d) => <Cell key={d.key} fill={STATUS_META[d.key]?.color} />)}
        </Pie>
        <Tooltip />
        <Legend verticalAlign="bottom" />
      </PieChart>
    </ResponsiveContainer>
  );
}
