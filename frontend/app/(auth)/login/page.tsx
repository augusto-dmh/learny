"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";

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
  const t = useTranslations("auth");
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("logIn")}</CardTitle>
        <CardDescription>{t("login.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <AuthForm mode="login" onAuthenticated={() => router.push("/home")} />
        <p className="text-sm text-muted-foreground">
          {t.rich("login.noAccount", {
            link: (chunks) => (
              <Link
                href="/register"
                className="text-primary underline-offset-4 hover:underline"
              >
                {chunks}
              </Link>
            ),
          })}
        </p>
      </CardContent>
    </Card>
  );
}
