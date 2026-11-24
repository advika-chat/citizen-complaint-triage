import { NavLink, Link, Route, Routes } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { ClipboardList, LayoutDashboard, MapPin } from "lucide-react";
import SubmitComplaint from "./pages/SubmitComplaint.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import ComplaintDetail from "./pages/ComplaintDetail.jsx";

export default function App() {
  return (
    <>
      <header className="app-header">
        <Link to="/" className="brand">
          <span className="brand-mark"><MapPin size={20} color="#fff" aria-hidden="true" /></span>
          <span>
            <div className="brand-title">Citizen Complaint Triage Bot</div>
            <div className="brand-tagline">Report it. Track it. Get it fixed.</div>
          </span>
        </Link>
        <nav className="nav" aria-label="Main">
          <NavLink to="/" end><ClipboardList size={16} aria-hidden="true" /> Submit</NavLink>
          <NavLink to="/dashboard"><LayoutDashboard size={16} aria-hidden="true" /> Dashboard</NavLink>
        </nav>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<SubmitComplaint />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/complaints/:id" element={<ComplaintDetail admin={false} />} />
          <Route path="/dashboard/complaints/:id" element={<ComplaintDetail admin={true} />} />
        </Routes>
      </main>
      <Toaster position="top-right" />
    </>
  );
}
