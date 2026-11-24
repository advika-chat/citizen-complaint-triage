import { useEffect, useState } from "react";
import { getLlmAnalytics } from "../api.js";

const pct = (x) => (x == null ? "-" : `${Math.round(x * 100)}%`);
const ms = (x) => (x == null ? "-" : `${Math.round(x)} ms`);

export default function LlmHealthCard({ refreshKey }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getLlmAnalytics().then(setData).catch((e) => setError(e.message));
  }, [refreshKey]);

  const metrics = data && [
    ["Success rate", pct(data.success_rate)],
    ["Fallback rate", pct(data.fallback_rate)],
    ["Latency p50", ms(data.p50_latency_ms)],
    ["Latency p95", ms(data.p95_latency_ms)],
    ["Calls", data.total_calls],
    ["Tokens", (data.prompt_tokens + data.completion_tokens).toLocaleString()],
    ["Est. cost", `$${data.est_cost_usd.toFixed(4)}`],
  ];

  return (
    <section className="card">
      <div className="card-header">
        <h2 className="section-title">LLM Health <span className="muted">(last 7 days)</span></h2>
        <span className="muted">Cost is an estimate; 0 on the free tier.</span>
      </div>
      {error && <div className="empty">Could not load LLM stats: {error}</div>}
      {data && data.total_calls === 0 && (
        <div className="empty">No LLM calls yet. Submissions use the fallback classifier until an API key is configured.</div>
      )}
      {data && data.total_calls > 0 && (
        <div className="llm-grid">
          {metrics.map(([label, value]) => (
            <div key={label}>
              <div className="stat-value">{value}</div>
              <div className="stat-label">{label}</div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
