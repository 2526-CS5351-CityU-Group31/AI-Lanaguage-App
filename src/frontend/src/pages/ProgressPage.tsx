/**
 * ProgressPage - home-style learning dashboard.
 *
 * Element: frontend progress page
 * Implements: FR-DASH-001; INV-PROG-001; ADR-008
 *
 * Values are rendered exactly as returned by the backend. The UI performs no
 * arithmetic and never derives, fabricates or overrides a progress total. The
 * CEFR badge reads the already-fetched AuthContext user (no extra GET /me).
 * Quick-action links use existing routes only.
 */
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { getProgress } from "../api/progress";
import type { CefrLevel, DashboardMetrics } from "../api/types";
import LoadingState from "../components/LoadingState";
import ErrorState from "../components/ErrorState";
import AppIcon, { type AppIconName } from "../components/AppIcon";

/**
 * Quick actions map to existing routes only. Writing feedback and grammar both
 * open the Chat page (its own mode selector covers those modes); no mode is
 * claimed to be preselected.
 */
const QUICK_ACTIONS: Array<{
  to: string;
  title: string;
  description: string;
  icon: AppIconName;
}> = [
  { to: "/chat", title: "Conversation practice", description: "Practise English conversation with the tutor.", icon: "conversation" },
  { to: "/chat", title: "Writing feedback", description: "Get feedback on your writing in the Chat page.", icon: "writing" },
  { to: "/chat", title: "Grammar practice", description: "Ask grammar questions in the Chat page.", icon: "grammar" },
  { to: "/vocabulary", title: "Vocabulary review", description: "Review vocabulary cards and set familiarity.", icon: "vocabulary" },
  { to: "/profile", title: "Profile", description: "View and update your CEFR level and goals.", icon: "profile" },
];

export default function ProgressPage({ level }: { level?: CefrLevel }) {
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await getProgress();
      setMetrics(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load progress.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  if (loading) {
    return <LoadingState label="Loading progress…" />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }

  if (!metrics) {
    return <ErrorState message="Unable to load progress." onRetry={load} />;
  }

  const levelBadge = level;

  return (
    <main className="page progress-page">
      <header className="dashboard-header">
        <h1>Welcome back</h1>
        {level ? (
          <span className="level-badge" aria-label={`Current CEFR level ${level}`}>
            {level}
          </span>
        ) : null}
      </header>

      <dl className="metrics">
        <div className="metric-card">
          <AppIcon name="sessions" />
          <dt>Sessions</dt>
          <dd data-testid="metric-sessions">{metrics.sessions}</dd>
        </div>
        <div className="metric-card">
          <AppIcon name="reviewed" />
          <dt>Words reviewed</dt>
          <dd data-testid="metric-words_reviewed">{metrics.words_reviewed}</dd>
        </div>
        <div className="metric-card">
          <AppIcon name="mastered" />
          <dt>Mastered vocabulary</dt>
          <dd data-testid="metric-mastered_vocabulary">{metrics.mastered_vocabulary}</dd>
        </div>
      </dl>

      <section className="dashboard-section" aria-label="Recent topics">
        <h2>Recent topics</h2>
        {metrics.recent_topics.length === 0 ? (
          <p className="hint">No recent topics yet.</p>
        ) : (
          <ul>
            {metrics.recent_topics.map((topic) => (
              <li key={topic}>{topic}</li>
            ))}
          </ul>
        )}
      </section>

      <section className="dashboard-section" aria-label="Quick actions">
        <h2>Quick actions</h2>
        <ul className="quick-actions">
          {QUICK_ACTIONS.map((action) => (
            <li key={action.title}>
              <Link className="card-link" to={action.to}>
                <span className="action-icon">
                  <AppIcon name={action.icon} />
                </span>
                <span className="action-copy">
                  <h3>{action.title}</h3>
                  <p>{action.description}</p>
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </main>
  );
}
