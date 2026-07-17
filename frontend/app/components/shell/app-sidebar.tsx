"use client";

/**
 * Library sidebar (FE-03/FE-04).
 *
 * Lists the signed-in user's sources with a status badge and, for ready
 * sources, a collapsible section tree fetched lazily from the structure
 * endpoint. Source entries link to Ask/Teach/Read; each tree section links to
 * the reader at that section's anchor. An empty library shows a pick-a-book
 * empty state with an upload affordance.
 *
 * Data fetching is client-side through the same-origin proxy (ADR-017); the
 * `(app)` shell owns the 401 → /login redirect via the header, so a load
 * failure here degrades to a readable message rather than crashing.
 */

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { fetchSourceStructure, listSources } from "@/app/lib/sources";
import type { SourceStructure, SourceSummary } from "@/app/lib/sources";
import { statusVariant } from "@/app/lib/status";
import { flattenSections } from "@/app/lib/tree";
import { Badge } from "@/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarMenuSubButton,
  SidebarMenuSubItem,
} from "@/components/ui/sidebar";

/**
 * The section tree under one ready source, rendered from the structure the
 * parent `SourceItem` fetched once and caches — collapsing and re-expanding
 * reuses it rather than re-fetching.
 */
function SourceTree({
  sourceId,
  structure,
  loading,
  error,
}: {
  sourceId: string;
  structure: SourceStructure | null;
  loading: boolean;
  error: string | null;
}) {
  if (loading) {
    return <p className="px-2 py-1 text-xs text-muted-foreground">Loading…</p>;
  }
  if (error) {
    return (
      <p role="alert" className="px-2 py-1 text-xs text-destructive">
        {error}
      </p>
    );
  }
  if (!structure) {
    return null;
  }

  const sections = flattenSections(structure.sections);
  if (sections.length === 0) {
    return (
      <p className="px-2 py-1 text-xs text-muted-foreground">No sections yet.</p>
    );
  }

  return (
    <SidebarMenuSub>
      {sections.map((section) => (
        <SidebarMenuSubItem key={`${section.anchor}-${section.label}`}>
          <SidebarMenuSubButton asChild>
            <Link
              href={`/sources/${sourceId}/read?anchor=${encodeURIComponent(
                section.anchor,
              )}`}
              style={{ paddingLeft: `${section.depth * 0.75}rem` }}
            >
              {section.title}
            </Link>
          </SidebarMenuSubButton>
        </SidebarMenuSubItem>
      ))}
    </SidebarMenuSub>
  );
}

/** One source row: title, status badge, action links, optional section tree. */
function SourceItem({ source }: { source: SourceSummary }) {
  const [open, setOpen] = useState(false);
  const isReady = source.status === "ready";
  // The section tree is fetched lazily on first expand and cached here (this row
  // stays mounted across collapse/re-expand), so re-expanding never re-fetches.
  const [structure, setStructure] = useState<SourceStructure | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const fetched = useRef(false);

  useEffect(() => {
    if (!open || fetched.current) {
      return;
    }
    fetched.current = true;
    let active = true;
    setLoading(true);
    setError(null);
    fetchSourceStructure(source.id)
      .then((next) => {
        if (active) setStructure(next);
      })
      .catch((err: unknown) => {
        if (active) {
          setError(
            err instanceof Error ? err.message : "Could not load the sections.",
          );
          // Let a later re-expand retry a failed fetch.
          fetched.current = false;
        }
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [open, source.id]);

  return (
    <SidebarMenuItem>
      <Collapsible open={open} onOpenChange={setOpen}>
        <div className="flex items-center gap-2 px-2 py-1">
          {isReady ? (
            <CollapsibleTrigger className="flex-1 text-left text-sm font-medium">
              {source.title}
            </CollapsibleTrigger>
          ) : (
            <span className="flex-1 text-sm font-medium">{source.title}</span>
          )}
          <Badge variant={statusVariant(source.status)}>{source.status}</Badge>
        </div>
        {isReady ? (
          <CollapsibleContent>
            <div className="flex gap-3 px-2 pb-1 text-xs">
              <Link
                href={`/sources/${source.id}/ask`}
                className="text-primary underline-offset-4 hover:underline"
              >
                Ask
              </Link>
              <Link
                href={`/sources/${source.id}/teach`}
                className="text-primary underline-offset-4 hover:underline"
              >
                Teach
              </Link>
              <Link
                href={`/sources/${source.id}/read`}
                className="text-primary underline-offset-4 hover:underline"
              >
                Read
              </Link>
            </div>
            {open ? (
              <SourceTree
                sourceId={source.id}
                structure={structure}
                loading={loading}
                error={error}
              />
            ) : null}
          </CollapsibleContent>
        ) : null}
      </Collapsible>
    </SidebarMenuItem>
  );
}

export function AppSidebar() {
  const [sources, setSources] = useState<SourceSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setSources(await listSources());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load your library.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Sidebar>
      <SidebarHeader className="px-2 py-3">
        <Link href="/sources" className="text-lg font-semibold">
          Learny
        </Link>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton asChild>
                  <Link href="/review">Review</Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup>
          <SidebarGroupLabel>Library</SidebarGroupLabel>
          <SidebarGroupContent>
            {error ? (
              <p role="alert" className="px-2 py-1 text-sm text-destructive">
                {error}
              </p>
            ) : sources === null ? (
              <p className="px-2 py-1 text-sm text-muted-foreground">Loading…</p>
            ) : sources.length === 0 ? (
              <div className="px-2 py-1 text-sm text-muted-foreground">
                <p>Your library is empty.</p>
                <Link
                  href="/sources"
                  className="text-primary underline-offset-4 hover:underline"
                >
                  Upload a book
                </Link>
              </div>
            ) : (
              <SidebarMenu>
                {sources.map((source) => (
                  <SourceItem key={source.id} source={source} />
                ))}
              </SidebarMenu>
            )}
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}
