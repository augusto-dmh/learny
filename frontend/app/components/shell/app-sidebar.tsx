"use client";

/**
 * App navigation sidebar (RFC-004 Cycle E — HOME-16).
 *
 * A small, stable primary nav: Home, Bookshelf, Review, Notes. The brand link
 * returns to Home. The per-source book list that used to live here is gone —
 * individual books are reached through the Bookshelf (`/sources`), and the
 * account surface lives in the header, not here.
 */

import Link from "next/link";

import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar";

const NAV_ITEMS = [
  { label: "Home", href: "/home" },
  { label: "Bookshelf", href: "/sources" },
  { label: "Review", href: "/review" },
  { label: "Notes", href: "/notes" },
] as const;

export function AppSidebar() {
  return (
    <Sidebar>
      <SidebarHeader className="px-2 py-3">
        <Link href="/home" className="text-lg font-semibold">
          Learny
        </Link>
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {NAV_ITEMS.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton asChild>
                    <Link href={item.href}>{item.label}</Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
    </Sidebar>
  );
}
