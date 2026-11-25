import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Overview", symbol: "⌂", end: true },
  { to: "/dashboard", label: "Workspace", symbol: "▦" },
  { to: "/patients/demo-patient-001", label: "Patient record", symbol: "◎" },
];

export default function Sidebar() {
  return (
    <aside className="sidebar">
      <p className="sidebar-label">Workspace</p>
      <nav className="nav-links" aria-label="Main navigation">
        {links.map(({ to, label, symbol, end }) => (
          <NavLink
            className={({ isActive }) => `nav-link${isActive ? " active" : ""}`}
            end={end}
            key={to}
            to={to}
          >
            <span className="nav-symbol" aria-hidden="true">
              {symbol}
            </span>
            {label}
          </NavLink>
        ))}
      </nav>
      <div className="sidebar-card">
        <strong>Clinical safety</strong>
        <p>Decision support prototype only. Review all source documents and findings.</p>
      </div>
    </aside>
  );
}
