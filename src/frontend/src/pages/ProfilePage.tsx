/**
 * ProfilePage - view and update learning profile.
 *
 * Element: frontend profile page
 * Implements: FR-PROF-001; INV-CEFR-001, INV-LANG-001; ADR-009
 *
 * The profile is loaded from the server; level choices are limited to A1-B2.
 * No language selector is offered (English only).
 */
import { useEffect, useState } from "react";
import { getMe } from "../api/auth";
import { apiRequest, ApiError } from "../api/client";
import LevelSelector from "../components/LevelSelector";
import LoadingState from "../components/LoadingState";
import ErrorState from "../components/ErrorState";
import type { CefrLevel, MeResponse, UpdateProfileRequest } from "../api/types";
import AppIcon from "../components/AppIcon";

export default function ProfilePage() {
  const [profile, setProfile] = useState<MeResponse | null>(null);
  const [level, setLevel] = useState<CefrLevel>("A1");
  const [goals, setGoals] = useState("");
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  async function load() {
    setLoading(true);
    setLoadError(null);
    try {
      const me = await getMe();
      setProfile(me);
      setLevel(me.cefr_level);
      setGoals(me.learning_goals ?? "");
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Unable to load profile.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleSave() {
    setSaving(true);
    setSaveMessage(null);
    setFieldErrors({});
    const payload: UpdateProfileRequest = { cefr_level: level, learning_goals: goals };
    try {
      const updated = await apiRequest<MeResponse>("/me", { method: "PATCH", body: payload });
      setProfile(updated);
      setSaveMessage("Profile saved.");
    } catch (err) {
      if (err instanceof ApiError) {
        setSaveMessage(err.message);
        setFieldErrors(err.fieldErrors ?? {});
      } else {
        setSaveMessage("Unable to save profile.");
      }
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <LoadingState label="Loading your profile…" />;
  }

  if (loadError) {
    return <ErrorState message={loadError} onRetry={load} />;
  }

  return (
    <main className="page profile-page">
      <header className="page-header">
        <h1>Profile</h1>
        <p>Manage your learning level and the goals that guide your English practice.</p>
      </header>

      {profile ? (
        <section className="profile-summary card" aria-label="Profile summary">
          <span className="profile-avatar"><AppIcon name="profile" /></span>
          <div className="profile-identity">
            <p className="profile-kicker">English learner</p>
            <p className="profile-email">{profile.email}</p>
          </div>
          <span className="level-badge" aria-label={`Current CEFR level ${profile.cefr_level}`}>
            {profile.cefr_level}
          </span>
        </section>
      ) : null}

      <section className="profile-form-card card" aria-labelledby="learning-settings-title">
        <div className="section-heading">
          <span className="section-icon"><AppIcon name="target" /></span>
          <div>
            <h2 id="learning-settings-title">Learning settings</h2>
            <p>Keep these details current so practice stays appropriate for your level.</p>
          </div>
        </div>

        {saveMessage ? (
          <p role="alert" className="form-message">
            {saveMessage}
          </p>
        ) : null}

        <div className="profile-fields">
          <div>
            <LevelSelector value={level} onChange={setLevel} />
            <p className="field-help">Choose from the supported A1–B2 learning levels.</p>
            {fieldErrors.cefr_level ? (
              <p role="alert" className="field-error">
                {fieldErrors.cefr_level}
              </p>
            ) : null}
          </div>

          <label htmlFor="goals" className="field goals-field">
            <span>Learning goals</span>
            <textarea
              id="goals"
              value={goals}
              onChange={(e) => setGoals(e.target.value)}
              rows={5}
              placeholder="For example: improve business writing or speak more confidently while travelling."
            />
            <span className="field-help">Describe what you would most like to improve.</span>
          </label>
        </div>

        <button className="save-profile-button" type="button" onClick={handleSave} disabled={saving}>
          <AppIcon name="check" />
          <span>{saving ? "Saving…" : "Save changes"}</span>
        </button>
      </section>
    </main>
  );
}
