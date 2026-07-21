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

export default function RegisterPage() {
  const router = useRouter();
  return (
    <Card>
      <CardHeader>
        <CardTitle>Create account</CardTitle>
        <CardDescription>Start learning with Learny.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <AuthForm
          mode="register"
          onAuthenticated={() => router.push("/home")}
        />
        <p className="text-sm text-muted-foreground">
          Already have an account?{" "}
          <Link
            href="/login"
            className="text-primary underline-offset-4 hover:underline"
          >
            Log in
          </Link>
          .
        </p>
      </CardContent>
    </Card>
  );
}
