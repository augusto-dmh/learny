"use client";

/**
 * Logged-in account panel with logout (D2).
 *
 * Resolves auth state via `/api/auth/me` (through the proxy) and renders the
 * signed-in user plus a logout button. Logout sends the session-bound CSRF
 * token in `X-CSRF-Token` (handled inside `auth.logout`, AD-007).
 *
 * The "Language" section stores the learner's interface language: Automatic
 * (negotiate from the browser), English or Português (Brasil). Like the AI
 * profile it is confirm-then-move: the backend stores the choice first, and only
 * a confirmed save writes the `learny_locale` cookie and asks the caller to
 * re-render (`onLocaleChanged`, `router.refresh()` on the page) — a failed save
 * leaves the cookie, the selection and the language untouched.
 *
 * When the deployment actually offers a generation-profile choice, the panel
 * also renders an "AI profile" section: "Operator default (recommended)" plus
 * one honest row per catalog profile. The section exists only when the catalog
 * is non-empty — absent, never a disabled shell — and any failure loading it
 * degrades to that absence rather than an error wall over the account content.
 * A stored id the catalog no longer contains renders as the default entry: the
 * UI never shows a phantom selection. Persisting a choice is not optimistic —
 * a failed save leaves the visible selection untouched and shows the
 * operation's catalog copy.
 *
 * The "Your own AI keys" section (`ProviderKeysSection`) follows: it renders
 * only when the instance offers learner keys, and owns its own requests.
 *
 * The `onRequireAuth` callback fires when the user is unauthenticated so the
 * caller can perform a UX-only redirect. NOTE: this redirect is convenience
 * only and is NOT the security boundary — FastAPI enforces auth on every
 * protected endpoint regardless of client-side routing (FR-AUTH-007).
 */

import { useTranslations } from "next-intl";
import { useCallback, useEffect, useState } from "react";

import {
  deleteAiProfileChoice,
  getAiProfileChoice,
  listAiProfiles,
  putAiProfileChoice,
  type LearnerProfile,
  type ProfileGrounding,
} from "@/app/lib/ai-profiles";
import { fetchAuthState, logout, type AuthState } from "@/app/lib/auth";
import { deleteLocale, putLocale, writeLocaleCookie } from "@/app/lib/locale";
import { ProviderKeysSection } from "@/app/components/provider-keys-section";
import { useErrorMessage } from "@/app/components/use-error-message";
import { LOCALES, isLocale, type AppLocale } from "@/i18n/config";
import { Button } from "@/components/ui/button";

const GROUNDING_KEY = {
  "verified-spans": "verifiedSpans",
  "prompt-cited": "promptCited",
  none: "none",
} as const satisfies Record<ProfileGrounding, string>;

/** Where the choice actually applies, as a key of `account.aiProfile.availability`. */
function availabilityKey(profile: LearnerProfile) {
  if (profile.ask_enabled && profile.teach_enabled) {
    return "both" as const;
  }
  if (profile.ask_enabled) {
    return "askOnly" as const;
  }
  if (profile.teach_enabled) {
    return "teachOnly" as const;
  }
  return "neither" as const;
}

export function AccountPanel({
  onRequireAuth,
  onLoggedOut,
  onLocaleChanged,
}: {
  onRequireAuth?: () => void;
  onLoggedOut?: () => void;
  /** Called after a confirmed language change has rewritten the cookie. */
  onLocaleChanged?: () => void;
}) {
  const t = useTranslations("account");
  const tLocale = useTranslations("common.locale");
  const tCommon = useTranslations("common");
  const errorMessage = useErrorMessage();
  const [state, setState] = useState<AuthState | null>(null);
  // null = not loaded (or failed to load): the section stays absent either way.
  const [catalog, setCatalog] = useState<LearnerProfile[] | null>(null);
  const [storedChoice, setStoredChoice] = useState<string | null>(null);
  const [aiPending, setAiPending] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);
  // The stored interface language; null = automatic.
  const [storedLocale, setStoredLocale] = useState<AppLocale | null>(null);
  const [localePending, setLocalePending] = useState(false);
  const [localeError, setLocaleError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    const next = await fetchAuthState();
    setState(next);
    if (next.authenticated) {
      setStoredLocale(isLocale(next.user.locale) ? next.user.locale : null);
    }
    // UX-only redirect for unauthenticated users (NOT the security boundary).
    if (!next.authenticated) {
      onRequireAuth?.();
    }
  }, [onRequireAuth]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const authenticated = state?.authenticated === true;
  useEffect(() => {
    if (!authenticated) {
      return;
    }
    let cancelled = false;
    void Promise.all([listAiProfiles(), getAiProfileChoice()])
      .then(([profiles, choice]) => {
        if (cancelled) {
          return;
        }
        setCatalog(profiles);
        setStoredChoice(choice.profile_id);
      })
      .catch((error: unknown) => {
        // Degrade to section-absent: a failed catalog or choice read must never
        // become an error wall over the rest of the account content. The cause
        // still lands in the console — an endpoint outage must not be
        // indistinguishable from an intentionally empty catalog for whoever
        // diagnoses it.
        console.warn("ai-profile section unavailable:", error);
        if (!cancelled) {
          setCatalog(null);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [authenticated]);

  async function handleLogout() {
    // Reuse the CSRF token already fetched on mount so logout is a single
    // round-trip (no extra /api/auth/me probe just to read the token).
    const csrfToken =
      state && state.authenticated ? state.user.csrf_token : undefined;
    await logout(csrfToken);
    setState({ authenticated: false });
    onLoggedOut?.();
  }

  /**
   * Persist a language. Nothing optimistic: the backend confirms first, then the
   * cookie (the render-time cache) is rewritten and the page re-renders.
   */
  async function handleChooseLocale(locale: AppLocale | null) {
    if (!state?.authenticated) {
      return;
    }
    setLocaleError(null);
    setLocalePending(true);
    try {
      if (locale === null) {
        await deleteLocale(state.user.csrf_token);
        setStoredLocale(null);
        writeLocaleCookie(null);
      } else {
        const stored = await putLocale(locale, state.user.csrf_token);
        setStoredLocale(stored);
        writeLocaleCookie(stored);
      }
      onLocaleChanged?.();
    } catch (error) {
      setLocaleError(errorMessage(error, locale === null ? "localeReset" : "localeSave"));
    } finally {
      setLocalePending(false);
    }
  }

  /**
   * Persist a choice. Nothing optimistic: the visible selection moves only
   * after the backend confirms, so a failed save changes nothing on screen.
   */
  async function handleChooseProfile(profileId: string | null) {
    if (!state?.authenticated) {
      return;
    }
    setAiError(null);
    setAiPending(true);
    try {
      if (profileId === null) {
        await deleteAiProfileChoice(state.user.csrf_token);
        setStoredChoice(null);
      } else {
        const stored = await putAiProfileChoice(profileId, state.user.csrf_token);
        setStoredChoice(stored.profile_id);
      }
    } catch (error) {
      setAiError(errorMessage(error, "aiProfileSave"));
    } finally {
      setAiPending(false);
    }
  }

  if (state === null) {
    return <p className="text-muted-foreground">{tCommon("loading")}</p>;
  }
  if (!state.authenticated) {
    return <p className="text-muted-foreground">{tCommon("signedOut")}</p>;
  }

  // A stored id absent from the catalog is stale (the operator renamed or
  // removed it): serving already fell back to the operator default, so the UI
  // renders exactly that — never a phantom selection.
  const effectiveChoice =
    catalog !== null &&
    storedChoice !== null &&
    catalog.some((profile) => profile.id === storedChoice)
      ? storedChoice
      : null;

  const localeOptions: { value: AppLocale | null; label: string }[] = [
    { value: null, label: t("language.automatic") },
    ...LOCALES.map((locale) => ({ value: locale, label: tLocale(`names.${locale}`) })),
  ];

  return (
    <section aria-label={t("regionLabel")} className="space-y-4">
      <p className="text-sm">
        {t.rich("signedInAs", {
          email: state.user.email,
          strong: (chunks) => <strong className="font-medium">{chunks}</strong>,
        })}
      </p>
      <section aria-label={t("language.heading")} className="space-y-3">
        <h2 className="text-sm font-medium">{t("language.heading")}</h2>
        <p className="text-sm text-muted-foreground">{t("language.intro")}</p>
        <div className="space-y-2">
          {localeOptions.map((option) => (
            <label key={option.value ?? "automatic"} className="flex items-center gap-2.5">
              <input
                type="radio"
                name="locale-choice"
                checked={storedLocale === option.value}
                onChange={() => void handleChooseLocale(option.value)}
                disabled={localePending}
                lang={option.value ?? undefined}
              />
              <span className="text-sm" lang={option.value ?? undefined}>
                {option.label}
              </span>
            </label>
          ))}
        </div>
        {localeError ? (
          <p role="alert" className="text-sm text-destructive">
            {localeError}
          </p>
        ) : null}
      </section>
      {catalog !== null && catalog.length > 0 ? (
        <section aria-label={t("aiProfile.heading")} className="space-y-3">
          <h2 className="text-sm font-medium">{t("aiProfile.heading")}</h2>
          <p className="text-sm text-muted-foreground">{t("aiProfile.intro")}</p>
          <div className="space-y-3">
            <label className="flex items-start gap-2.5">
              <input
                type="radio"
                name="ai-profile-choice"
                checked={effectiveChoice === null}
                onChange={() => void handleChooseProfile(null)}
                disabled={aiPending}
                aria-label={t("aiProfile.defaultTitle")}
                className="mt-1"
              />
              <span>
                <span className="block text-sm">{t("aiProfile.defaultTitle")}</span>
                <span className="block text-xs text-muted-foreground">
                  {t("aiProfile.defaultHint")}
                </span>
              </span>
            </label>
            {catalog.map((profile) => (
              <label key={profile.id} className="flex items-start gap-2.5">
                <input
                  type="radio"
                  name="ai-profile-choice"
                  checked={effectiveChoice === profile.id}
                  onChange={() => void handleChooseProfile(profile.id)}
                  disabled={aiPending}
                  aria-label={profile.display_name}
                  className="mt-1"
                />
                <span>
                  <span className="block text-sm">{profile.display_name}</span>
                  {profile.description ? (
                    <span className="block text-sm text-muted-foreground">
                      {profile.description}
                    </span>
                  ) : null}
                  <span className="block text-xs text-muted-foreground">
                    {t(`aiProfile.grounding.${GROUNDING_KEY[profile.grounding]}`)}{" "}
                    {t(`aiProfile.availability.${availabilityKey(profile)}`)}
                  </span>
                </span>
              </label>
            ))}
          </div>
          {aiError ? (
            <p role="alert" className="text-sm text-destructive">
              {aiError}
            </p>
          ) : null}
        </section>
      ) : null}
      <ProviderKeysSection csrfToken={state.user.csrf_token} />
      <Button type="button" variant="outline" onClick={handleLogout}>
        {t("logout")}
      </Button>
    </section>
  );
}
