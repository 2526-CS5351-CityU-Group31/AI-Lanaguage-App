/**
 * Shared API types for the learner UI.
 *
 * Element: frontend API contract types (display layer only)
 * Implements: FR-AUTH-001, FR-PROF-001, FR-CHAT-001, FR-FEED-001, FR-RAG-001,
 *             FR-VOC-001, FR-VOC-002, FR-DASH-001; ADR-005, ADR-008, ADR-009
 *
 * Authority note: the frontend never computes identity, citations, scope
 * status or progress values. These types mirror server payloads only.
 */

/** INV-CEFR-001: canonical levels only. */
export const CEFR_LEVELS = ["A1", "A2", "B1", "B2"] as const;
export type CefrLevel = (typeof CEFR_LEVELS)[number];

/** INV-LANG-001: English only; no language selector in the UI. */
export type Language = "en";

/** FR-AUTH-001 / INV-AUTH-001: identity is server-derived, never client-set. */
export interface MeResponse {
  id: string;
  email: string;
  language: Language;
  cefr_level: CefrLevel;
  learning_goals: string | null;
}

export interface RegisterRequest {
  email: string;
  password: string;
  language: Language;
}

export interface LoginRequest {
  email: string;
  password: string;
}

/** FR-PROF-001: profile update; level validated client-side and server-side. */
export interface UpdateProfileRequest {
  cefr_level?: CefrLevel;
  learning_goals?: string;
}

/**
 * LearnerMode - UI-level practice selection (distinct from TutorTask).
 * FR-CHAT-001
 */
export type LearnerMode =
  | "conversation_practice"
  | "writing_feedback"
  | "grammar_question"
  | "vocabulary_question"
  | "lesson_question";

/** TutorTask - server-level task per ADR-005 (display-only mirror). */
export type TutorTask = "conversation" | "writing_feedback" | "lesson_help";

/**
 * Mapping from learner mode to tutor task. Deterministic display mapping;
 * the backend remains authoritative for routing. vocabulary_question is NOT a
 * tutor task - it routes to the vocabulary API path.
 * Implements: FR-CHAT-001, FR-VOC-001
 */
export const LEARNER_MODE_TO_TUTOR_TASK: Record<
  Exclude<LearnerMode, "vocabulary_question">,
  TutorTask
> = {
  conversation_practice: "conversation",
  writing_feedback: "writing_feedback",
  grammar_question: "lesson_help",
  lesson_question: "lesson_help",
};

/**
 * ScopeStatus - server scope verdict, separate from the tutor response.
 * Implements: INV-SCOPE-002, INV-SCOPE-004, INV-SCOPE-005
 * Insufficient evidence is NOT a scope status; it is ADR-005 abstained=true.
 */
export type ScopeStatus = "accepted" | "rejected" | "uncertain" | "mixed";

/** INV-CITE-001: citation rendered by server-provided metadata, lookup by id. */
export interface SourceMetadata {
  source_id: string;
  title: string;
  section: string;
}

/**
 * ADR-005 validated structured response contract (display mirror).
 * Implements: FR-CHAT-001, FR-FEED-001, FR-RAG-001, INV-CITE-001
 */
export interface ChatResponse {
  task: TutorTask;
  abstained: boolean;
  source_ids: string[];
  answer: string;
  follow_up?: string;
  tips?: string[];
  suggested_text?: string;
  explanation?: string;
  examples?: string[];
  validation_id: string;
  sources?: SourceMetadata[];
}

/** Chat turn payload; learner_mode drives routing server-side. */
export interface SendMessageRequest {
  learner_mode: LearnerMode;
  message: string;
  topic?: string;
  request_id: string;
}

/** Optional scope verdict returned alongside a turn. */
export interface ScopeResult {
  scope_status: ScopeStatus;
  scope_message: string;
}

export interface ChatTurnResponse extends Partial<ScopeResult> {
  task?: TutorTask;
  abstained?: boolean;
  source_ids?: string[];
  answer?: string;
  follow_up?: string;
  tips?: string[];
  suggested_text?: string;
  explanation?: string;
  examples?: string[];
  validation_id?: string;
  sources?: SourceMetadata[];
}

/** FR-VOC-001: published vocabulary card. Field names are provisional. */
export interface VocabularyCard {
  entry_id: string;
  word: string;
  sense: string;
  definition: string;
  example: string;
  level: CefrLevel;
  topic: string;
}

/** FR-VOC-002: three-tier familiarity state. */
export type FamiliarityState = "learning" | "familiar" | "mastered";

export interface RecordFamiliarityRequest {
  state: FamiliarityState;
}

/** FR-DASH-001 / INV-PROG-001: server-projected aggregates, rendered verbatim. */
export interface DashboardMetrics {
  sessions: number;
  words_reviewed: number;
  mastered_vocabulary: number;
  recent_topics: string[];
}

/** Normalized error surfaced by the API client. */
export interface ApiErrorBody {
  error_code: string;
  message: string;
  field_errors?: Record<string, string>;
}
