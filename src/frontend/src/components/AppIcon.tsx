/**
 * AppIcon - reusable decorative line icons for learner navigation and cards.
 *
 * Element: frontend presentation layer
 * Implements: FR-AUTH-001, FR-DASH-001; ADR-008, ADR-009; VS-16
 *
 * Icons never carry meaning on their own: adjacent visible text supplies the
 * accessible name, while every SVG is hidden from assistive technology.
 */
export type AppIconName =
  | "practice"
  | "vocabulary"
  | "progress"
  | "profile"
  | "logout"
  | "conversation"
  | "writing"
  | "grammar"
  | "sessions"
  | "reviewed"
  | "mastered"
  | "lesson"
  | "send"
  | "email"
  | "target"
  | "check";

export default function AppIcon({ name }: { name: AppIconName }) {
  const common = {
    fill: "none",
    stroke: "currentColor",
    strokeWidth: 1.8,
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
  };

  return (
    <svg
      className={`app-icon app-icon-${name}`}
      viewBox="0 0 24 24"
      aria-hidden="true"
      focusable="false"
      {...common}
    >
      {name === "practice" || name === "conversation" ? (
        <>
          <path d="M5 5.5h10a3 3 0 0 1 3 3v4a3 3 0 0 1-3 3H10l-4 3v-3H5a3 3 0 0 1-3-3v-4a3 3 0 0 1 3-3Z" />
          <path d="M7 10.5h6M7 13h4" />
        </>
      ) : null}
      {name === "vocabulary" ? (
        <>
          <path d="M4 4.5h6a3 3 0 0 1 3 3v12a3 3 0 0 0-3-3H4Z" />
          <path d="M20 4.5h-4a3 3 0 0 0-3 3v12a3 3 0 0 1 3-3h4Z" />
        </>
      ) : null}
      {name === "progress" ? (
        <>
          <path d="M4 19V9M10 19V5M16 19v-7M22 19V3" />
          <path d="M2 19.5h21" />
        </>
      ) : null}
      {name === "profile" ? (
        <>
          <circle cx="12" cy="8" r="3.5" />
          <path d="M5 20a7 7 0 0 1 14 0" />
        </>
      ) : null}
      {name === "logout" ? (
        <>
          <path d="M10 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h5" />
          <path d="M14 8l4 4-4 4M8 12h10" />
        </>
      ) : null}
      {name === "writing" ? (
        <>
          <path d="M4 20l4.5-1 10-10a2.1 2.1 0 0 0-3-3l-10 10L4 20Z" />
          <path d="m14.5 7.5 3 3M4 4h7" />
        </>
      ) : null}
      {name === "grammar" ? (
        <>
          <path d="M5 19 10 5h4l5 14M7 14h10" />
          <path d="M3 5h4" />
        </>
      ) : null}
      {name === "sessions" ? (
        <>
          <rect x="3" y="5" width="18" height="15" rx="2" />
          <path d="M7 3v4M17 3v4M3 10h18" />
        </>
      ) : null}
      {name === "reviewed" ? (
        <>
          <path d="M5 4h11a2 2 0 0 1 2 2v14H7a2 2 0 0 1-2-2Z" />
          <path d="M8 8h7M8 12h7M8 16h4" />
        </>
      ) : null}
      {name === "mastered" ? (
        <>
          <circle cx="12" cy="10" r="6" />
          <path d="m9.5 10 1.7 1.7 3.5-3.5M8 15.5 7 21l5-2 5 2-1-5.5" />
        </>
      ) : null}
      {name === "lesson" ? (
        <>
          <path d="M4 5.5h11a3 3 0 0 1 3 3v11H7a3 3 0 0 1-3-3Z" />
          <path d="M8 9h6M8 12h6M8 15h3M18 8.5h2v8h-2" />
        </>
      ) : null}
      {name === "send" ? (
        <>
          <path d="m3 4 18 8-18 8 3-8Z" />
          <path d="M6 12h15" />
        </>
      ) : null}
      {name === "email" ? (
        <>
          <rect x="3" y="5" width="18" height="14" rx="2" />
          <path d="m4 7 8 6 8-6" />
        </>
      ) : null}
      {name === "target" ? (
        <>
          <circle cx="12" cy="12" r="8" />
          <circle cx="12" cy="12" r="3" />
          <path d="M15 9 21 3M17 3h4v4" />
        </>
      ) : null}
      {name === "check" ? <path d="m5 12 4 4L19 6" /> : null}
    </svg>
  );
}
