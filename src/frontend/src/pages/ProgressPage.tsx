/**
 * ProgressPage - dashboard of server-projected learning metrics.
 *
 * Element: frontend progress page
 * Implements: FR-DASH-001; INV-PROG-001; ADR-008
 *
 * Values are rendered exactly as returned by the backend. The UI performs no
 * arithmetic and never derives or overrides a progress total.
 */
import { useEffect, useState } from "react";
import { getProgress } from "../api/progress";
import type { DashboardMetrics } from "../api/types";
import LoadingState from "../components/LoadingState";
import ErrorState from "../components/ErrorState";

export default function ProgressPage() {
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

  return (
    <main className="page progress-page">
      <h1>Progress</h1>
      <dl className="metrics">
        <div className="metric-card">
          <dt>Sessions</dt>
          <dd data-testid="metric-sessions">{metrics.sessions}</dd>
        </div>
        <div className="metric-card">
          <dt>Words reviewed</dt>
          <dd data-testid="metric-words_reviewed">{metrics.words_reviewed}</dd>
        </div>
        <div className="metric-card">
          <dt>Mastered vocabulary</dt>
          <dd data-testid="metric-mastered_vocabulary">{metrics.mastered_vocabulary}</dd>
        </div>
      </dl>

      <section aria-label="Recent topics">
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
    </main>
  );
}
