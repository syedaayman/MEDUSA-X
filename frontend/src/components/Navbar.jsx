import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getHealth } from "../services/api.js";

export default function Navbar() {
  const [health, setHealth] = useState(null);
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getHealth()
      .then((data) => {
        if (!cancelled) {
          setHealth(data);
          setOffline(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setHealth(null);
          setOffline(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <header className="topbar">
      <Link className="brand" to="/">
        <span className="brand-mark" aria-hidden="true">
          M
        </span>
        <span>
          <strong>MEDUSA-X</strong>
          <small>Clinical record intelligence</small>
        </span>
      </Link>
      <div className="topbar-actions">
        <span className="topbar-status">
          {offline ? "API offline" : health ? "API connected" : "Checking API…"}
        </span>
      </div>
    </header>
  );
}
