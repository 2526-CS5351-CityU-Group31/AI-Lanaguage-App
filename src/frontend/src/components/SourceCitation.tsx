/**
 * SourceCitation - renders a citation only from server-provided metadata.
 *
 * Element: frontend citation display
 * Implements: FR-RAG-001; INV-CITE-001
 *
 * A citation is shown only when a matching server source exists for the
 * source_id. The UI never synthesizes titles, sections or URLs.
 */
import type { SourceMetadata } from "../api/types";

export default function SourceCitation({
  sourceIds,
  sources,
}: {
  sourceIds: string[];
  sources: SourceMetadata[] | undefined;
}) {
  if (!sources || sources.length === 0) {
    return null;
  }

  const resolved = sourceIds
    .map((id) => sources.find((s) => s.source_id === id))
    .filter((s): s is SourceMetadata => Boolean(s));

  if (resolved.length === 0) {
    return null;
  }

  return (
    <ul className="citations" aria-label="Lesson sources">
      {resolved.map((source) => (
        <li key={source.source_id}>
          <span className="citation-source" aria-label="Source">
            <strong>{source.title}</strong>
            {source.section ? <span> — {source.section}</span> : null}
          </span>
        </li>
      ))}
    </ul>
  );
}
