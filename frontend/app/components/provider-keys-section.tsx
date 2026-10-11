"use client";

/**
 * The account page's "Your own AI keys" section (ADR-0033).
 *
 * A learner on an instance whose operator enabled it pastes a provider key,
 * tests it, replaces it or deletes it, and sees which profiles it powers. The
 * section exists only when the backend reports `enabled: true`; a disabled
 * feature or a failed load leaves it absent, never an error wall over the
 * account page.
 *
 * The key lives in this component only while the learner types it: a confirmed
 * save clears the input and the row then shows `•••• last4`. Nothing ever
 * renders a key again, because nothing ever returns one. Every action is
 * confirmed-then-moved: a failed save, test or delete shows an inline error and
 * leaves the row as it was. Delete asks first, inline, without a browser dialog.
 */

import { useLocale, useTranslations } from "next-intl";
import { useEffect, useState } from "react";

import {
  deleteProviderKey,
  listProviderKeys,
  putProviderKey,
  testProviderKey,
  type KeyProvider,
  type KeyTestResult,
  type PoweredProfile,
  type ProviderKeyRow,
} from "@/app/lib/provider-keys";
import { useErrorMessage } from "@/app/components/use-error-message";
import { Button } from "@/components/ui/button";

/** Where a powered profile applies, as a key of `account.providerKeys.profileModes`. */
function modesKey(profile: PoweredProfile) {
  if (profile.ask && profile.teach) {
    return "both" as const;
  }
  if (profile.ask) {
    return "askOnly" as const;
  }
  if (profile.teach) {
    return "teachOnly" as const;
  }
  return "neither" as const;
}

export function ProviderKeysSection({ csrfToken }: { csrfToken: string }) {
  const t = useTranslations("account.providerKeys");
  const [rows, setRows] = useState<ProviderKeyRow[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    void listProviderKeys()
      .then((keys) => {
        if (!cancelled) {
          setRows(keys.enabled ? keys.providers : null);
        }
      })
      .catch((error: unknown) => {
        // Degrade to section-absent, as the AI-profile section does; the cause
        // still reaches the console for whoever diagnoses it.
        console.warn("provider-keys section unavailable:", error);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (rows === null || rows.length === 0) {
    return null;
  }

  function replaceRow(next: ProviderKeyRow) {
    setRows((current) =>
      current ? current.map((row) => (row.provider === next.provider ? next : row)) : current,
    );
  }

  return (
    <section aria-label={t("heading")} className="space-y-3">
      <h2 className="text-sm font-medium">{t("heading")}</h2>
      <p className="text-sm text-muted-foreground">{t("intro")}</p>
      <p className="text-sm text-muted-foreground">{t("disclosure")}</p>
      <ul className="space-y-4">
        {rows.map((row) => (
          <ProviderKeyItem
            key={row.provider}
            row={row}
            csrfToken={csrfToken}
            onChanged={replaceRow}
          />
        ))}
      </ul>
    </section>
  );
}

type Pending = "save" | "test" | "delete" | null;

function ProviderKeyItem({
  row,
  csrfToken,
  onChanged,
}: {
  row: ProviderKeyRow;
  csrfToken: string;
  onChanged: (next: ProviderKeyRow) => void;
}) {
  const t = useTranslations("account.providerKeys");
  const tCommon = useTranslations("common");
  const locale = useLocale();
  const errorMessage = useErrorMessage();
  const [draft, setDraft] = useState("");
  const [editing, setEditing] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [pending, setPending] = useState<Pending>(null);
  const [error, setError] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<KeyTestResult | null>(null);
  const provider: KeyProvider = row.provider;
  const showInput = !row.configured || editing;

  async function handleSave() {
    if (!draft) {
      return;
    }
    setError(null);
    setTestResult(null);
    setPending("save");
    try {
      const saved = await putProviderKey(provider, draft, csrfToken);
      setDraft("");
      setEditing(false);
      onChanged(saved);
    } catch (caught) {
      setError(errorMessage(caught, "providerKeySave"));
    } finally {
      setPending(null);
    }
  }

  async function handleTest() {
    setError(null);
    setTestResult(null);
    setPending("test");
    try {
      setTestResult(await testProviderKey(provider, csrfToken));
    } catch (caught) {
      setError(errorMessage(caught, "providerKeyTest"));
    } finally {
      setPending(null);
    }
  }

  async function handleDelete() {
    setError(null);
    setTestResult(null);
    setPending("delete");
    try {
      await deleteProviderKey(provider, csrfToken);
      setConfirmingDelete(false);
      setEditing(false);
      onChanged({ ...row, configured: false, last4: null, added_at: null });
    } catch (caught) {
      setError(errorMessage(caught, "providerKeyDelete"));
    } finally {
      setPending(null);
    }
  }

  const busy = pending !== null;

  return (
    <li className="space-y-2" data-provider={provider}>
      <p className="text-sm font-medium">{row.label}</p>
      {row.configured ? (
        <p className="text-sm">
          <span className="font-mono">{t("masked", { last4: row.last4 ?? "" })}</span>
          {row.added_at ? (
            <span className="ml-2 text-xs text-muted-foreground">
              {t("addedOn", {
                // The library's date pattern: the browser's own time zone.
                date: new Intl.DateTimeFormat(locale, { dateStyle: "medium" }).format(
                  new Date(row.added_at),
                ),
              })}
            </span>
          ) : null}
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">{t("notConfigured")}</p>
      )}
      <div className="text-xs text-muted-foreground">
        <span>{t("powers")}</span>
        <ul className="ml-4 list-disc">
          {row.powers.map((profile) => (
            <li key={profile.profile_id}>
              {t(`profileModes.${modesKey(profile)}`, { name: profile.display_name })}
            </li>
          ))}
          {row.powers_cards ? <li>{t("cards")}</li> : null}
        </ul>
      </div>
      {showInput ? (
        <form
          className="flex flex-wrap items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            void handleSave();
          }}
        >
          <input
            type="password"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            aria-label={t("inputLabel", { provider: row.label })}
            placeholder={t("placeholder")}
            autoComplete="off"
            spellCheck={false}
            disabled={busy}
            className="min-w-0 flex-1 rounded-md border border-input bg-background px-2 py-1 text-sm"
          />
          <Button type="submit" size="sm" disabled={busy || !draft}>
            {pending === "save" ? t("saving") : t("save")}
          </Button>
          {editing ? (
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => {
                setDraft("");
                setEditing(false);
              }}
            >
              {tCommon("cancel")}
            </Button>
          ) : null}
        </form>
      ) : null}
      {row.configured && !editing ? (
        <div className="flex flex-wrap gap-2">
          <Button type="button" size="sm" variant="outline" disabled={busy} onClick={handleTest}>
            {pending === "test" ? t("testing") : t("test")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => {
              setTestResult(null);
              setEditing(true);
            }}
          >
            {t("replace")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => setConfirmingDelete(true)}
          >
            {t("delete")}
          </Button>
        </div>
      ) : null}
      {confirmingDelete ? (
        <div role="group" className="space-y-2 rounded-md border border-border p-2">
          <p className="text-sm">{t("confirmDelete", { provider: row.label })}</p>
          <div className="flex gap-2">
            <Button
              type="button"
              size="sm"
              variant="destructive"
              disabled={busy}
              onClick={handleDelete}
            >
              {t("confirmDeleteAction")}
            </Button>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              disabled={busy}
              onClick={() => setConfirmingDelete(false)}
            >
              {tCommon("cancel")}
            </Button>
          </div>
        </div>
      ) : null}
      {testResult ? (
        <p role="status" className="text-sm">
          {testResult.ok ? t("testResult.ok") : t(`testResult.${testResult.reason}`)}
        </p>
      ) : null}
      {error ? (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      ) : null}
    </li>
  );
}
