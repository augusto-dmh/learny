/**
 * Section-tree helpers shared by the library sidebar and the teach target picker
 * (FE-04). Generalizes the depth-first flatten that lived privately in
 * `TeachPanel`, so both the sidebar's navigable tree and the picker read one
 * source of truth. Pure transform over the structure endpoint's nested
 * `StructureSection[]` — no fetching, no DOM.
 */

import { type StructureSection } from "./sources";

/** One section flattened out of the nested tree, keeping its depth and path. */
export type FlatSection = {
  anchor: string;
  title: string;
  depth: number;
  /** Full breadcrumb, section titles joined by " › " (picker label). */
  label: string;
};

/** Flatten the nested section tree into a depth-first list, preserving order. */
export function flattenSections(sections: StructureSection[]): FlatSection[] {
  const out: FlatSection[] = [];
  for (const section of sections) {
    out.push({
      anchor: section.anchor,
      title: section.title,
      depth: section.depth,
      label: section.section_path.join(" › "),
    });
    out.push(...flattenSections(section.children));
  }
  return out;
}
