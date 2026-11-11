/**
 * MSW request handlers - test-only backend contract stubs.
 *
 * Element: frontend test harness (test-only, never shipped to production)
 * Implements: V1-V4 verification constraints
 *
 * These handlers encode the ASSUMED backend contracts from the approved plan
 * and are marked provisional. They exist so the UI can be tested without a
 * live backend. Production data never flows through this file.
 *
 * Unconfirmed (provisional) contracts referenced here:
 * - Citation metadata shape        (assumed: sources[{source_id,title,section}])
 * - Chat request fields            (assumed: {learner_mode,message,topic?,request_id})
 * - Vocabulary field names         (assumed: definition / example unless backend differs)
 */
import { http, HttpResponse } from "msw";

const api = "/api";

export const testMe = {
  user_id: "user_test_001",
  email: "learner@example.com",
  language: "en",
  cefr_level: "B1",
  learning_goals: "Improve business writing",
};

const dashboardMetrics = {
  sessions: 7,
  words_reviewed: 42,
  mastered_vocabulary: 11,
  recent_topics: ["travel", "work"],
};

const vocabularyCard = {
  entry_id: "voc_001",
  word: "resilient",
  sense: "able to recover quickly",
  definition: "Able to recover quickly from difficulty.",
  example: "She stayed resilient after the setback.",
  level: "B1",
  topic: "work",
};

export const handlers = [
  http.post(`${api}/auth/register`, async ({ request }) => {
    const body = (await request.json()) as {
      email?: string;
      password?: string;
      cefr_level?: string;
      language?: string;
    };
    if (body.language && body.language !== "en") {
      return HttpResponse.json(
        { error_code: "invalid_language", message: "Only English is supported." },
        { status: 422 },
      );
    }
    if (!body.email || !body.password || !body.cefr_level) {
      return HttpResponse.json(
        {
          error_code: "validation_error",
          message: "email, password and cefr_level are required.",
          field_errors: { cefr_level: "Required" },
        },
        { status: 422 },
      );
    }
    return HttpResponse.json({ session_token: "test_session_token" }, { status: 200 });
  }),

  http.post(`${api}/auth/login`, async ({ request }) => {
    const body = (await request.json()) as { email?: string; password?: string };
    if (!body.email || !body.password) {
      return HttpResponse.json(
        {
          error_code: "invalid_credentials",
          message: "Email and password are required.",
          field_errors: { email: "Required", password: "Required" },
        },
        { status: 422 },
      );
    }
    return HttpResponse.json({ session_token: "test_session_token" }, { status: 200 });
  }),

  http.post(`${api}/auth/logout`, () => HttpResponse.json({ ok: true }, { status: 200 })),

  http.get(`${api}/me`, () => {
    return HttpResponse.json(testMe, { status: 200 });
  }),

  http.patch(`${api}/me`, async ({ request }) => {
    const body = (await request.json()) as { cefr_level?: string };
    const allowed = ["A1", "A2", "B1", "B2"];
    if (body.cefr_level && !allowed.includes(body.cefr_level)) {
      return HttpResponse.json(
        {
          error_code: "invalid_cefr",
          message: "Level must be one of A1, A2, B1, B2.",
          field_errors: { cefr_level: "Invalid CEFR level." },
        },
        { status: 422 },
      );
    }
    return HttpResponse.json({ ...testMe, ...body }, { status: 200 });
  }),

  http.get(`${api}/vocabulary/random`, () => HttpResponse.json([vocabularyCard], { status: 200 })),

  http.post(`${api}/me/vocabulary/:entryId`, async ({ request, params }) => {
    const body = (await request.json()) as { state?: string };
    const allowed = ["learning", "familiar", "mastered"];
    if (!body.state || !allowed.includes(body.state)) {
      return HttpResponse.json(
        {
          error_code: "invalid_state",
          message: "Unknown familiarity state.",
          field_errors: { state: "Invalid state." },
        },
        { status: 422 },
      );
    }
    return HttpResponse.json({ entry_id: params.entryId, state: body.state }, { status: 200 });
  }),

  http.get(`${api}/me/progress`, () => HttpResponse.json(dashboardMetrics, { status: 200 })),

  http.get(`${api}/forbidden`, () =>
    HttpResponse.json({ error_code: "forbidden", message: "Not found." }, { status: 404 }),
  ),
];
