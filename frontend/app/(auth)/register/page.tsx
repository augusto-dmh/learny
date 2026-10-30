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

export default function RegisterPage() {
  const router = useRouter();
  const t = useTranslations("auth");
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t("createAccount")}</CardTitle>
        <CardDescription>{t("register.description")}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <AuthForm
          mode="register"
          onAuthenticated={() => router.push("/home")}
        />
        <p className="text-sm text-muted-foreground">
          {t.rich("register.haveAccount", {
            link: (chunks) => (
              <Link
                href="/login"
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
