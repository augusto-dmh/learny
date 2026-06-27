"use client";

import { useRouter } from "next/navigation";

import { AuthForm } from "@/app/components/AuthForm";

export default function LoginPage() {
  const router = useRouter();
  return (
    <main>
      <h1>Log in</h1>
      <AuthForm mode="login" onAuthenticated={() => router.push("/account")} />
      <p>
        No account? <a href="/register">Create one</a>.
      </p>
    </main>
  );
}
