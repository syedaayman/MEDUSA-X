import { Link } from "react-router-dom";

export default function Navbar() {
  return (
    <header className="topbar">
      <Link className="brand" to="/" aria-label="MEDUSA-X home">
        <span className="brand-mark" aria-hidden="true">
          M
        </span>
        <span>MEDUSA-X</span>
      </Link>
      <div className="topbar-note">
        <span className="status-dot" aria-hidden="true" />
        Prototype · synthetic data only
      </div>
    </header>
  );
}
