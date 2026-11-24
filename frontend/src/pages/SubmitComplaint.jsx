import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";
import { ImagePlus, LocateFixed, Send, X } from "lucide-react";
import { createComplaint } from "../api.js";
import { CategoryBadge, StatusBadge, UrgencyBadge } from "../components/Badges.jsx";

const MAX = 4000;
const ACCEPT = "image/jpeg,image/png,image/webp,image/gif";

export default function SubmitComplaint() {
  const [text, setText] = useState("");
  const [photo, setPhoto] = useState(null);
  const [preview, setPreview] = useState(null);
  const [coords, setCoords] = useState(null);
  const [locating, setLocating] = useState(false);
  const [locError, setLocError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState(null);

  useEffect(() => {
    if (!photo) {
      setPreview(null);
      return undefined;
    }
    const url = URL.createObjectURL(photo);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [photo]);

  function useMyLocation() {
    setLocError("");
    if (!navigator.geolocation) {
      setLocError("Geolocation is not supported by this browser.");
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setCoords({ latitude: pos.coords.latitude, longitude: pos.coords.longitude });
        setLocating(false);
      },
      (err) => {
        setLocError(err.message || "Could not get your location.");
        setLocating(false);
      },
      { timeout: 10000 }
    );
  }

  async function submit(e) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const created = await createComplaint({ text: text.trim(), photo, ...(coords || {}) });
      setResult(created);
      setText("");
      setPhoto(null);
      setCoords(null);
      toast.success("Complaint submitted");
    } catch (err) {
      toast.error(err.message);
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="narrow">
      <h1 className="page-title">Submit a Complaint</h1>
      <p className="page-subtitle">
        Describe the problem in your own words. Our assistant will categorise it and route it to the right department.
        Please do not include personal information.
      </p>

      <form className="card" onSubmit={submit}>
        <label className="field" htmlFor="text">What is the problem?</label>
        <textarea
          id="text" value={text} maxLength={MAX} required
          placeholder="e.g. The streetlight outside my building has been off for a week."
          onChange={(e) => setText(e.target.value)}
        />
        <div className="char-count">{text.length} / {MAX}</div>

        <div className="form-row" style={{ alignItems: "stretch", flexDirection: "column" }}>
          {preview ? (
            <div className="photo-preview">
              <img src={preview} alt="Selected upload preview" />
              <span style={{ flex: 1, minWidth: 0, overflowWrap: "anywhere" }}>{photo.name}</span>
              <button type="button" className="icon-btn" aria-label="Remove photo" onClick={() => setPhoto(null)}>
                <X size={16} />
              </button>
            </div>
          ) : (
            <label className="photo-drop">
              <ImagePlus size={20} aria-hidden="true" />
              <span>Add a photo (optional) - JPEG, PNG, WebP or GIF, up to 5MB</span>
              <input type="file" accept={ACCEPT} hidden onChange={(e) => setPhoto(e.target.files[0] || null)} />
            </label>
          )}
        </div>

        <div className="form-row">
          <button type="button" className="btn secondary" onClick={useMyLocation} disabled={locating}>
            <LocateFixed size={16} aria-hidden="true" /> {locating ? "Locating..." : "Use my location"}
          </button>
          {coords && (
            <span className="muted">Location set: {coords.latitude.toFixed(4)}, {coords.longitude.toFixed(4)}</span>
          )}
          {locError && <span style={{ color: "var(--danger)" }}>{locError}</span>}
        </div>

        <button className="btn" type="submit" disabled={!text.trim() || submitting}>
          {submitting ? <><span className="spinner" /> Submitting...</> : <><Send size={16} aria-hidden="true" /> Submit complaint</>}
        </button>
      </form>

      {result && (
        <section className="card result-card" aria-live="polite">
          <h2 className="section-title">Thanks, we have your report</h2>
          <p style={{ fontSize: 16, margin: "8px 0" }}>{result.summary}</p>
          <dl>
            <dt>Category</dt><dd><CategoryBadge category={result.category} /></dd>
            <dt>Urgency</dt><dd><UrgencyBadge urgency={result.urgency} /></dd>
            <dt>Suggested department</dt><dd>{result.suggested_department}</dd>
            <dt>Status</dt><dd><StatusBadge status={result.status} /></dd>
          </dl>
          {result.duplicate_of && (
            <p className="muted">
              Possible duplicate of an existing report.{" "}
              <Link to={`/complaints/${result.duplicate_of}`}>View the existing report</Link>
            </p>
          )}
          <Link className="btn-link" to={`/complaints/${result.id}`}>Track this complaint</Link>
        </section>
      )}
    </div>
  );
}
