import { useCallback, useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import toast from "react-hot-toast";
import { ArrowLeft, MapPin } from "lucide-react";
import { addNote, getComplaint, photoUrl, updateComplaintStatus } from "../api.js";
import { CATEGORY_META, STATUSES, formatDate, statusLabel } from "../constants.js";
import { CategoryBadge, StatusBadge, UrgencyBadge } from "../components/Badges.jsx";

export default function ComplaintDetail({ admin }) {
  const { id } = useParams();
  const [complaint, setComplaint] = useState(null);
  const [original, setOriginal] = useState(null); // the complaint this one duplicates
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [noteText, setNoteText] = useState("");
  const [saving, setSaving] = useState(false);

  const base = admin ? "/dashboard/complaints" : "/complaints";

  const load = useCallback(async () => {
    try {
      const c = await getComplaint(id);
      setComplaint(c);
      setNotFound(false);
      setOriginal(c.duplicate_of ? await getComplaint(c.duplicate_of).catch(() => null) : null);
    } catch {
      setNotFound(true);
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    setLoading(true);
    load();
  }, [load]);

  async function changeStatus(status) {
    setSaving(true);
    try {
      await updateComplaintStatus(id, status);
      await addNote(id, `Status updated to "${statusLabel(status)}".`);
      await load();
      toast.success(`Marked ${statusLabel(status)}`);
    } catch (e) {
      toast.error(e.message);
    } finally {
      setSaving(false);
    }
  }

  async function submitNote(e) {
    e.preventDefault();
    setSaving(true);
    try {
      await addNote(id, noteText.trim());
      setNoteText("");
      await load();
      toast.success("Note added");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSaving(false);
    }
  }

  const back = (
    <Link to={admin ? "/dashboard" : "/"} className="btn ghost small" style={{ marginBottom: 12 }}>
      <ArrowLeft size={14} aria-hidden="true" /> Back
    </Link>
  );

  if (loading) {
    return (
      <div className="narrow">{back}
        <div className="card"><div className="skeleton" style={{ height: 28, width: "60%" }} /><div className="skeleton skeleton-row" /><div className="skeleton skeleton-row" /></div>
      </div>
    );
  }
  if (notFound || !complaint) {
    return <div className="narrow">{back}<div className="card empty">We could not find that complaint.</div></div>;
  }

  const Icon = CATEGORY_META[complaint.category]?.icon;
  const photo = photoUrl(complaint.photo_url);

  return (
    <div className="narrow">
      {back}
      <section className="card">
        <div className="detail-head">
          <div className="detail-title">
            <div className="detail-icon">{Icon && <Icon size={22} aria-hidden="true" />}</div>
            <div style={{ minWidth: 0 }}>
              <h1 className="page-title" style={{ fontSize: 22 }}>{complaint.summary}</h1>
              <div className="muted">Complaint ID: <span className="mono">{complaint.id}</span></div>
            </div>
          </div>
          {admin ? (
            <select aria-label="Status" value={complaint.status} disabled={saving} style={{ width: "auto" }} onChange={(e) => changeStatus(e.target.value)}>
              {STATUSES.map((s) => <option key={s} value={s}>{statusLabel(s)}</option>)}
            </select>
          ) : (
            <StatusBadge status={complaint.status} />
          )}
        </div>

        <div className="badges" style={{ marginTop: 14 }}>
          <CategoryBadge category={complaint.category} />
          <UrgencyBadge urgency={complaint.urgency} suffix=" urgency" />
          {admin && <StatusBadge status={complaint.status} />}
          {complaint.latitude != null && (
            <span className="badge"><MapPin size={12} aria-hidden="true" /> {complaint.latitude.toFixed(4)}, {complaint.longitude.toFixed(4)}</span>
          )}
        </div>

        {photo && <img className="detail-photo" src={photo} alt="Photo submitted with the complaint" />}

        <h2 className="section-title" style={{ marginTop: 16 }}>Original report</h2>
        <p className="original">{complaint.raw_text}</p>
        <h2 className="section-title">Suggested department</h2>
        <p>{complaint.suggested_department}</p>
      </section>

      {complaint.duplicate_of && (
        <section className="card">
          <span className="badge dup">Possible duplicate</span>{" "}
          of <Link to={`${base}/${complaint.duplicate_of}`}>{original ? original.summary : "an existing report"}</Link>
        </section>
      )}

      <section className="card">
        <h2 className="section-title" style={{ marginBottom: 14 }}>Status Timeline</h2>
        <ul className="timeline">
          <li><strong>Complaint submitted</strong><time>{formatDate(complaint.created_at, true)}</time></li>
          {complaint.notes.map((n) => (
            <li key={n.id}>{n.text}<time>{formatDate(n.created_at, true)}</time></li>
          ))}
        </ul>
        {admin && (
          <form className="note-form" onSubmit={submitNote}>
            <textarea aria-label="Add a note" placeholder="Add a note for the timeline..." value={noteText} onChange={(e) => setNoteText(e.target.value)} />
            <button className="btn" type="submit" disabled={!noteText.trim() || saving}>Add</button>
          </form>
        )}
      </section>

      {admin && <TriagePanel complaint={complaint} />}
    </div>
  );
}

function TriagePanel({ complaint }) {
  const trace = complaint.agent_trace;
  return (
    <section className="card">
      <details className="triage">
        <summary>How this was triaged</summary>
        <p>
          Model: <strong>{complaint.model ?? "none"}</strong> &middot; Prompt: <strong>{complaint.prompt_version ?? "none"}</strong> &middot;{" "}
          Fallback used: <strong>{complaint.used_fallback ? "yes" : "no"}</strong>
        </p>
        {Array.isArray(trace) && trace.length > 0 ? (
          trace.map((step, i) => (
            <div className="trace-step" key={i}>
              {step.type === "final" ? (
                <><strong>Final reasoning:</strong> {step.reasoning}</>
              ) : (
                <>
                  <strong>Turn {step.turn}: {step.tool}</strong>
                  <div className="mono">{JSON.stringify(step.arguments)}</div>
                  <div>{step.result}</div>
                </>
              )}
            </div>
          ))
        ) : (
          <p className="muted">No tool calls were recorded for this complaint.</p>
        )}
      </details>
    </section>
  );
}
