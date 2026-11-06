/**
 * VocabularyPage - random vocabulary review with familiarity state.
 *
 * Element: frontend vocabulary page
 * Implements: FR-VOC-001, FR-VOC-002; ADR-008
 *
 * Cards and field names come from the backend (definition_en / example_en
 * unless the backend specifies otherwise). Familiarity changes are recorded
 * server-side; the UI does not compute mastery.
 */
import { useEffect, useState } from "react";
import { getRandomVocabulary, recordFamiliarity } from "../api/vocabulary";
import { ApiError } from "../api/client";
import type { FamiliarityState, VocabularyCard as VocabCard } from "../api/types";
import VocabularyCard from "../components/VocabularyCard";
import LoadingState from "../components/LoadingState";
import ErrorState from "../components/ErrorState";
import EmptyState from "../components/EmptyState";

export default function VocabularyPage() {
  const [cards, setCards] = useState<VocabCard[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const data = await getRandomVocabulary({ count: 5 });
      setCards(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to load vocabulary.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function handleStateChange(entryId: string, state: FamiliarityState) {
    setSaving(true);
    setActionError(null);
    try {
      await recordFamiliarity(entryId, state);
    } catch (err) {
      if (err instanceof ApiError) {
        const fieldMessage = err.fieldErrors ? Object.values(err.fieldErrors).join(" ") : "";
        setActionError(fieldMessage || err.message);
      } else {
        setActionError("Unable to save your review.");
      }
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <LoadingState label="Loading vocabulary…" />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={load} />;
  }

  if (!cards || cards.length === 0) {
    return <EmptyState message="No vocabulary available right now." />;
  }

  return (
    <main className="page vocabulary-page">
      <h1>Vocabulary</h1>
      {actionError ? <ErrorState message={actionError} /> : null}
      <div className="vocab-list">
        {cards.map((card) => (
          <VocabularyCard
            key={card.entry_id}
            card={card}
            saving={saving}
            onStateChange={handleStateChange}
          />
        ))}
      </div>
    </main>
  );
}
