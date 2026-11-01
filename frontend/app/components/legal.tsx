import type { ReactNode } from "react";

/**
 * Shared rendering for the public legal pages (privacy, terms, copyright).
 *
 * The pages hold no English copy of their own: every heading and paragraph
 * comes from the catalogs (`legal.*`), so the hard-coded-string sensor has no
 * exemption to carry for them. Section bodies are catalog strings split into
 * blocks on blank lines; a block whose lines all start with "- " renders as a
 * list, so the LGPD rights enumeration stays a real list in both locales.
 */

export function LegalSection({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section>
      <h2 className="text-lg font-semibold">{title}</h2>
      {children}
    </section>
  );
}

function isListItemBlock(block: string): boolean {
  const lines = block.split("\n").filter((line) => line.trim().length > 0);
  return lines.length > 0 && lines.every((line) => line.trimStart().startsWith("- "));
}

function listItems(block: string): string[] {
  return block
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line.startsWith("- "))
    .map((line) => line.slice(2));
}

export function LegalParagraphs({ body }: { body: string }) {
  const blocks = body
    .split("\n\n")
    .map((block) => block.trim())
    .filter((block) => block.length > 0);
  return (
    <>
      {blocks.map((block, index) =>
        isListItemBlock(block) ? (
          <ul key={index} className="list-disc space-y-1 pl-6">
            {listItems(block).map((item, itemIndex) => (
              <li key={itemIndex}>{item}</li>
            ))}
          </ul>
        ) : (
          <p key={index}>{block}</p>
        ),
      )}
    </>
  );
}
