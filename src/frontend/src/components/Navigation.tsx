/**
 * Navigation - primary learner navigation (dashboard sidebar).
 *
 * Element: frontend navigation
 * Implements: FR-AUTH-001; VS-16
 *
 * Renders the product name and the four existing destinations. Logout uses the
 * existing handler passed from App. No avatars, flags, scores or unsupported
 * features are added.
 */
import { NavLink } from "react-router-dom";
import AppIcon, { type AppIconName } from "./AppIcon";

const LINKS: Array<{ to: string; label: string; icon: AppIconName }> = [
  { to: "/chat", label: "Practice", icon: "practice" },
  { to: "/vocabulary", label: "Vocabulary", icon: "vocabulary" },
  { to: "/progress", label: "Progress", icon: "progress" },
  { to: "/profile", label: "Profile", icon: "profile" },
];

export default function Navigation({ onLogout }: { onLogout?: () => void }) {
  return (
    <nav className="app-nav" aria-label="Main navigation">
      <p className="brand">English Companion</p>
      <ul>
        {LINKS.map((link) => (
          <li key={link.to}>
            <NavLink to={link.to}>
              <AppIcon name={link.icon} />
              <span>{link.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
      {onLogout ? (
        <button className="nav-logout" type="button" onClick={onLogout}>
          <AppIcon name="logout" />
          <span>Log out</span>
        </button>
      ) : null}
    </nav>
  );
}