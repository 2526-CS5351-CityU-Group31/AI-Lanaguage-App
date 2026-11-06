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
      setGoals(me.learning_goals);
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
      <h1>Profile</h1>
      {profile ? <p className="profile-email">{profile.email}</p> : null}

      {saveMessage ? (
        <p role="alert" className="form-message">
          {saveMessage}
        </p>
      ) : null}

      <LevelSelector value={level} onChange={setLevel} />
      {fieldErrors.cefr_level ? (
        <p role="alert" className="field-error">
          {fieldErrors.cefr_level}
        </p>
      ) : null}

      <label htmlFor="goals" className="field">
        <span>Learning goals</span>
        <textarea
          id="goals"
          value={goals}
          onChange={(e) => setGoals(e.target.value)}
          rows={3}
        />
      </label>

      <button type="button" onClick={handleSave} disabled={saving}>
        {saving ? "Saving…" : "Save"}
      </button>
    </main>
  );
}
