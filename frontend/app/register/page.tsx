"use client";

import { useRouter } from "next/navigation";

import { AuthForm } from "@/app/components/AuthForm";

export default function RegisterPage() {
  const router = useRouter();
  return (
    <main>
      <h1>Create account</h1>
      <AuthForm mode="register" onAuthenticated={() => router.push("/account")} />
      <p>
        Already have an account? <a href="/login">Log in</a>.
      </p>
    </main>
  );
}
