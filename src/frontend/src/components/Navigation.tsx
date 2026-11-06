/**
 * Navigation - primary learner navigation bar.
 *
 * Element: frontend navigation
 * Implements: FR-AUTH-001; VS-16
 */
import { NavLink } from "react-router-dom";

const LINKS = [
  { to: "/chat", label: "Practice" },
  { to: "/vocabulary", label: "Vocabulary" },
  { to: "/progress", label: "Progress" },
  { to: "/profile", label: "Profile" },
];

export default function Navigation({ onLogout }: { onLogout?: () => void }) {
  return (
    <nav className="app-nav" aria-label="Main navigation">
      <ul>
        {LINKS.map((link) => (
          <li key={link.to}>
            <NavLink to={link.to}>{link.label}</NavLink>
          </li>
        ))}
      </ul>
      {onLogout ? (
        <button type="button" onClick={onLogout}>
          Log out
        </button>
      ) : null}
    </nav>
  );
}
