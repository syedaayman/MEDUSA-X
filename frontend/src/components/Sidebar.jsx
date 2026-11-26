import { NavLink } from "react-router-dom";

const navGroups = [
  {
    label: "Workspace",
    items: [
      { to: "/", label: "Overview", end: true, icon: "dashboard" },
      { to: "/dashboard", label: "Patients", end: false, icon: "patients" },
    ],
  },
];

function Icon({ name }) {
  const common = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round" };
  switch (name) {
    case "dashboard":
      return <svg {...common}><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="7" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /><rect x="14" y="14" width="7" height="7" rx="1" /></svg>;
    case "patients":
      return <svg {...common}><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2" /><circle cx="9" cy="7" r="4" /><path d="M23 21v-2a4 4 0 0 0-3-3.87" /><path d="M16 3.13a4 4 0 0 1 0 7.75" /></svg>;
    default:
      return <svg {...common}><circle cx="12" cy="12" r="10" /></svg>;
  }
}

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="brand-mark" aria-hidden="true">M</span>
        <div className="brand-text">
          <strong>MEDUSA-X</strong>
          <small>Clinical Record Intelligence</small>
        </div>
      </div>

      {navGroups.map((group) => (
        <div className="sidebar-group" key={group.label}>
          <p className="sidebar-group-label">{group.label}</p>
          <nav aria-label={group.label}>
            {group.items.map((link) => (
              <NavLink
                className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
                end={link.end}
                key={link.to}
                to={link.to}
              >
                <span className="nav-icon" aria-hidden="true"><Icon name={link.icon} /></span>
                <span className="nav-label">{link.label}</span>
              </NavLink>
            ))}
          </nav>
        </div>
      ))}

      <div className="sidebar-note">
        <p>Prototype notice: synthetic demonstration data only. MEDUSA-X does not diagnose, prescribe, or decide which record is correct.</p>
      </div>
    </aside>
  );
}
