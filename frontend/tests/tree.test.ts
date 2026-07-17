/**
 * FE-04 — `flattenSections` turns the structure endpoint's nested section tree
 * into the depth-first list the sidebar navigates and the teach picker labels.
 *
 * Pins the contract both callers depend on: reading order is preserved
 * depth-first (parent before its children, siblings in order), each entry keeps
 * its own `depth`, and `label` is the full breadcrumb (`section_path` joined by
 * " › ") the picker renders.
 */

import { describe, expect, it } from "vitest";

import { type StructureSection } from "../app/lib/sources";
import { flattenSections } from "../app/lib/tree";

/** A ≥3-deep tree with branching so depth-first order is observable. */
const tree: StructureSection[] = [
  {
    title: "Part I",
    depth: 0,
    section_path: ["Part I"],
    anchor: "p1.xhtml",
    children: [
      {
        title: "Chapter 1",
        depth: 1,
        section_path: ["Part I", "Chapter 1"],
        anchor: "p1.xhtml#c1",
        children: [
          {
            title: "Section A",
            depth: 2,
            section_path: ["Part I", "Chapter 1", "Section A"],
            anchor: "p1.xhtml#c1-a",
            children: [
              {
                title: "Detail A.1",
                depth: 3,
                section_path: ["Part I", "Chapter 1", "Section A", "Detail A.1"],
                anchor: "p1.xhtml#c1-a-1",
                children: [],
              },
            ],
          },
          {
            title: "Section B",
            depth: 2,
            section_path: ["Part I", "Chapter 1", "Section B"],
            anchor: "p1.xhtml#c1-b",
            children: [],
          },
        ],
      },
      {
        title: "Chapter 2",
        depth: 1,
        section_path: ["Part I", "Chapter 2"],
        anchor: "p1.xhtml#c2",
        children: [],
      },
    ],
  },
  {
    title: "Part II",
    depth: 0,
    section_path: ["Part II"],
    anchor: "p2.xhtml",
    children: [],
  },
];

describe("flattenSections", () => {
  it("emits sections depth-first, parents before children, siblings in order", () => {
    const flat = flattenSections(tree);

    expect(flat.map((s) => s.title)).toEqual([
      "Part I",
      "Chapter 1",
      "Section A",
      "Detail A.1",
      "Section B",
      "Chapter 2",
      "Part II",
    ]);
    // The anchors track the same order, so navigation targets line up.
    expect(flat.map((s) => s.anchor)).toEqual([
      "p1.xhtml",
      "p1.xhtml#c1",
      "p1.xhtml#c1-a",
      "p1.xhtml#c1-a-1",
      "p1.xhtml#c1-b",
      "p1.xhtml#c2",
      "p2.xhtml",
    ]);
  });

  it("carries each section's own depth through the flatten", () => {
    const flat = flattenSections(tree);

    expect(flat.map((s) => s.depth)).toEqual([0, 1, 2, 3, 2, 1, 0]);
  });

  it("derives the breadcrumb label from the full section path", () => {
    const flat = flattenSections(tree);
    const byTitle = new Map(flat.map((s) => [s.title, s.label]));

    expect(byTitle.get("Part I")).toBe("Part I");
    expect(byTitle.get("Detail A.1")).toBe(
      "Part I › Chapter 1 › Section A › Detail A.1",
    );
    expect(byTitle.get("Chapter 2")).toBe("Part I › Chapter 2");
  });

  it("returns nothing for an empty tree", () => {
    expect(flattenSections([])).toEqual([]);
  });
});
