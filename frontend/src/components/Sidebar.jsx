import { NavLink } from "react-router-dom";

const links = [
  { to: "/dashboard", label: "Workspace", hint: "Patients and uploads" },
  { to: "/", label: "Overview", hint: "What MEDUSA-X does", end: true },
];

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <nav aria-label="Main navigation">
        {links.map((link) => (
          <NavLink
            className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
            end={link.end}
            key={link.to}
            to={link.to}
          >
            <span>{link.label}</span>
            <small>{link.hint}</small>
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-note">
        <strong>Prototype notice</strong>
        <p>
          Findings are potential discrepancies for clinician review. MEDUSA-X does not diagnose,
          prescribe or decide which record is correct.
        </p>
      </div>
    </aside>
  );
}
