import type { ReactNode } from "react";

import { AppSidebar } from "@/app/components/shell/app-sidebar";
import { AuthHeader } from "@/app/components/shell/auth-header";
import { SidebarProvider } from "@/components/ui/sidebar";

/**
 * Shell for every authenticated route (FE-03): the library sidebar plus a header
 * with the user's email, account link, logout, and theme toggle. The hosted
 * pages own their own `<main>`, so the shell wraps them in a plain flex column
 * rather than `SidebarInset` to avoid nesting `<main>` elements.
 */
export default function AppLayout({ children }: { children: ReactNode }) {
  return (
    <SidebarProvider>
      <AppSidebar />
      <div className="flex min-h-svh w-full flex-1 flex-col">
        <AuthHeader />
        {children}
      </div>
    </SidebarProvider>
  );
}
