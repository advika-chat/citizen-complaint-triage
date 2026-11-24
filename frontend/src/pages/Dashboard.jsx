import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { AlertTriangle, CheckCircle2, CircleDot, ClipboardList, Search } from "lucide-react";
import {
  bulkUpdateStatus, getAnalyticsSummary, getComplaints, getHealth, searchComplaints, updateComplaintStatus,
} from "../api.js";
import { CATEGORIES, STATUSES, URGENCIES, categoryLabel, statusLabel } from "../constants.js";
import StatTile from "../components/StatTile.jsx";
import ComplaintMap from "../components/ComplaintMap.jsx";
import ComplaintTable from "../components/ComplaintTable.jsx";
import AnalyticsChart from "../components/AnalyticsChart.jsx";
import StatusChart from "../components/StatusChart.jsx";
import TrendChart from "../components/TrendChart.jsx";
import LlmHealthCard from "../components/LlmHealthCard.jsx";

const PAGE_SIZE = 10;

export default function Dashboard() {
  const navigate = useNavigate();
  const [analytics, setAnalytics] = useState(null);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState("keyword");
  const [llmConfigured, setLlmConfigured] = useState(false);
  const [filters, setFilters] = useState({ category: "", urgency: "", status: "" });
  const [sort, setSort] = useState("created_at");
  const [order, setOrder] = useState("desc");
  const [page, setPage] = useState(0);
  const [selected, setSelected] = useState(new Set());
  const [refreshKey, setRefreshKey] = useState(0);
  const requestId = useRef(0);

  // debounce search input
  useEffect(() => {
    const t = setTimeout(() => {
      setQuery(search.trim());
      setPage(0);
    }, 350);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => {
    getHealth().then((h) => setLlmConfigured(h.semantic_search)).catch(() => {});
  }, []);

  const loadAnalytics = useCallback(() => {
    getAnalyticsSummary().then(setAnalytics).catch((e) => toast.error(e.message));
    setRefreshKey((k) => k + 1);
  }, []);
  useEffect(loadAnalytics, [loadAnalytics]);

  const semantic = mode === "meaning" && query !== "";

  const loadComplaints = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    try {
      let result;
      if (semantic) {
        const found = await searchComplaints(query, 50);
        const rows = found.items ?? found;
        const filtered = rows.filter(
          (c) => (!filters.category || c.category === filters.category)
            && (!filters.urgency || c.urgency === filters.urgency)
            && (!filters.status || c.status === filters.status)
        );
        result = { items: filtered.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE), total: filtered.length };
      } else {
        result = await getComplaints({ ...filters, q: query, sort, order, limit: PAGE_SIZE, offset: page * PAGE_SIZE });
      }
      if (id !== requestId.current) return; // a newer request superseded this one
      setItems(result.items);
      setTotal(result.total);
    } catch (e) {
      if (id === requestId.current) {
        toast.error(e.message);
        setItems([]);
        setTotal(0);
      }
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [filters, query, sort, order, page, semantic]);
  useEffect(() => { loadComplaints(); }, [loadComplaints]);

  const setFilter = (key) => (e) => {
    setFilters((f) => ({ ...f, [key]: e.target.value }));
    setPage(0);
  };

  function onSort(field) {
    if (field === sort) setOrder((o) => (o === "asc" ? "desc" : "asc"));
    else { setSort(field); setOrder("desc"); }
    setPage(0);
  }

  async function onStatusChange(c, status) {
    const previous = c.status;
    setItems((rows) => rows.map((r) => (r.id === c.id ? { ...r, status } : r)));
    try {
      await updateComplaintStatus(c.id, status);
      toast.success(`Marked ${statusLabel(status)}`);
      loadAnalytics();
    } catch (e) {
      setItems((rows) => rows.map((r) => (r.id === c.id ? { ...r, status: previous } : r)));
      toast.error(e.message);
    }
  }

  async function bulk(status) {
    try {
      await bulkUpdateStatus([...selected], status);
      toast.success(`${selected.size} complaints marked ${statusLabel(status)}`);
      setSelected(new Set());
      loadComplaints();
      loadAnalytics();
    } catch (e) {
      toast.error(e.message);
    }
  }

  const toggle = (id) => setSelected((s) => {
    const next = new Set(s);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });
  const toggleAll = () => setSelected((s) => {
    const everySelected = items.length > 0 && items.every((c) => s.has(c.id));
    return everySelected ? new Set() : new Set(items.map((c) => c.id));
  });

  const totalAll = analytics ? Object.values(analytics.by_status).reduce((a, b) => a + b, 0) : null;
  const from = total === 0 ? 0 : page * PAGE_SIZE + 1;
  const to = Math.min(total, (page + 1) * PAGE_SIZE);

  return (
    <div className="dashboard-grid">
      <div>
        <h1 className="page-title">Admin Dashboard</h1>
        <p className="page-subtitle">Review incoming complaints, update their status and watch trends.</p>
      </div>

      <div className="stat-tiles">
        <StatTile icon={ClipboardList} label="Total Complaints" value={totalAll} color="#4f46e5" soft="var(--brand-soft)" />
        <StatTile icon={CircleDot} label="Open" value={analytics?.by_status.open} color="#3b82f6" soft="var(--info-soft)" />
        <StatTile icon={AlertTriangle} label="High Urgency" value={analytics?.by_urgency.high} color="#e5484d" soft="var(--danger-soft)" />
        <StatTile icon={CheckCircle2} label="Resolved" value={analytics?.by_status.resolved} color="#30a46c" soft="var(--success-soft)" />
      </div>

      <section className="card">
        <div className="card-header"><h2 className="section-title">Complaint Map</h2></div>
        <ComplaintMap items={items} />
      </section>

      <section className="card">
        <div className="card-header"><h2 className="section-title">Complaints</h2></div>
        <div className="toolbar">
          <div className="search-wrap">
            <Search size={16} aria-hidden="true" />
            <input
              type="search" aria-label="Search complaints" value={search}
              placeholder={mode === "meaning" ? "Search by meaning..." : "Search text..."}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>
          <div className="toggle" role="group" aria-label="Search mode">
            <button type="button" className={mode === "keyword" ? "on" : ""} onClick={() => { setMode("keyword"); setPage(0); }}>Keyword</button>
            <button
              type="button" className={mode === "meaning" ? "on" : ""} disabled={!llmConfigured}
              title={llmConfigured ? "Semantic search" : "Needs an LLM API key on the backend"}
              onClick={() => { setMode("meaning"); setPage(0); }}
            >By meaning</button>
          </div>
          <div className="filters">
            <select aria-label="Filter by category" value={filters.category} onChange={setFilter("category")}>
              <option value="">All categories</option>
              {CATEGORIES.map((c) => <option key={c} value={c}>{categoryLabel(c)}</option>)}
            </select>
            <select aria-label="Filter by urgency" value={filters.urgency} onChange={setFilter("urgency")}>
              <option value="">All urgencies</option>
              {URGENCIES.map((u) => <option key={u} value={u}>{u[0].toUpperCase() + u.slice(1)}</option>)}
            </select>
            <select aria-label="Filter by status" value={filters.status} onChange={setFilter("status")}>
              <option value="">All statuses</option>
              {STATUSES.map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
            </select>
          </div>
        </div>

        {selected.size > 0 && (
          <div className="bulk-bar">
            <strong>{selected.size} selected</strong>
            {STATUSES.map((s) => (
              <button key={s} className="btn secondary small" onClick={() => bulk(s)}>Mark {statusLabel(s)}</button>
            ))}
            <button className="btn ghost small" onClick={() => setSelected(new Set())}>Clear</button>
          </div>
        )}

        <ComplaintTable
          items={items} loading={loading} selected={selected} onToggle={toggle} onToggleAll={toggleAll}
          sort={sort} order={order} onSort={onSort} onOpen={(id) => navigate(`/dashboard/complaints/${id}`)}
          onStatusChange={onStatusChange} showSimilarity={semantic}
        />

        <div className="pagination">
          <span>{from}&ndash;{to} of {total}</span>
          <button className="btn secondary small" disabled={page === 0} onClick={() => setPage((p) => p - 1)}>Prev</button>
          <button className="btn secondary small" disabled={to >= total} onClick={() => setPage((p) => p + 1)}>Next</button>
        </div>
      </section>

      <div className="charts-row">
        <section className="card"><h2 className="section-title">By Category</h2><AnalyticsChart byCategory={analytics?.by_category} /></section>
        <section className="card"><h2 className="section-title">By Status</h2><StatusChart byStatus={analytics?.by_status} /></section>
        <section className="card"><h2 className="section-title">Last 14 Days</h2><TrendChart trend={analytics?.trend} /></section>
      </div>

      <LlmHealthCard refreshKey={refreshKey} />
    </div>
  );
}
