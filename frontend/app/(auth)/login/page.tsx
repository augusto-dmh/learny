"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { AuthForm } from "@/app/components/AuthForm";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function LoginPage() {
  const router = useRouter();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Log in</CardTitle>
        <CardDescription>Welcome back to Learny.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <AuthForm mode="login" onAuthenticated={() => router.push("/home")} />
        <p className="text-sm text-muted-foreground">
          No account?{" "}
          <Link
            href="/register"
            className="text-primary underline-offset-4 hover:underline"
          >
            Create one
          </Link>
          .
        </p>
      </CardContent>
    </Card>
  );
}
