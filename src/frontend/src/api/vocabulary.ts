/**
 * Vocabulary API adapter.
 *
 * Element: frontend vocabulary client
 * Implements: FR-VOC-001, FR-VOC-002; ADR-008
 *
 * Provisional field names: definition / example unless the backend
 * specifies otherwise.
 */
import { apiRequest } from "./client";
import type { FamiliarityState, VocabularyCard } from "./types";

export function getRandomVocabulary(params?: {
  level?: string;
  topic?: string;
  count?: number;
}): Promise<VocabularyCard[]> {
  const query = new URLSearchParams();
  if (params?.level) query.set("level", params.level);
  if (params?.topic) query.set("topic", params.topic);
  if (params?.count) query.set("count", String(params.count));
  const suffix = query.toString() ? `?${query.toString()}` : "";
  return apiRequest<VocabularyCard[]>(`/vocabulary/random${suffix}`);
}

export function recordFamiliarity(
  entryId: string,
  state: FamiliarityState,
): Promise<unknown> {
  return apiRequest<unknown>(`/me/vocabulary/${entryId}`, {
    method: "POST",
    body: { state },
  });
}
