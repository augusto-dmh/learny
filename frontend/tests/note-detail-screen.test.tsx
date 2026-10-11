// @vitest-environment jsdom

/**
 * NF-13/14 gate (component) — the note detail screen. It loads a note and its
 * backlinks, edits the body in a textarea with a preview toggle, enables Save only
 * while dirty and persists the edit (re-baselining afterward), lists anchored
 * passages with a jump-back link for a live anchor and a distinct badge + quote
 * snapshot for an orphaned one (NF-14), links each backlink to its note, flags an
 * over-cap save, and deletes behind a confirm before returning to the list.
 */

import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { NoteDetailScreen } from "../app/components/notes/note-detail-screen";
import { expectNoEnglishCopy } from "./i18n-copy";
import { setTestLocale } from "./setup-intl";

const nav = vi.hoisted(() => ({ push: vi.fn() }));
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: nav.push, replace: vi.fn() }),
}));

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT =
    true;
});

type Handler = (init: RequestInit) => Promise<Response> | Response;

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function routedFetch(handlers: Record<string, Handler>) {
  return vi.fn(async (url: string, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${url}`;
    const handler = handlers[key];
    if (!handler) throw new Error(`unexpected fetch: ${key}`);
    return handler(init ?? {});
  });
}

const authedMe = jsonResponse(200, {
  id: "u1",
  email: "a@b.c",
  created_at: "now",
  csrf_token: "csrf-xyz",
});

const liveAnchor = {
  id: "a1",
  source_id: "s1",
  source_title: "Ready Book",
  anchor: "chapter-1.xhtml#core-idea",
  section_path: ["Chapter 1", "Core Idea"],
  block_ordinal: 0,
  start_offset: 0,
  end_offset: 5,
  quote_exact: "Ada wrote the first algorithm",
  quote_prefix: "",
  quote_suffix: "",
  status: "active",
};

const orphanAnchor = {
  ...liveAnchor,
  id: "a2",
  // Distinct identifiers from the live anchor: if the jump-back gate ever
  // inverts, the rendered link would carry THIS href and the assertion on the
  // live href below fails — the shared-fixture blind spot a mutation survived.
  source_id: "s9",
  anchor: "chapter-9.xhtml#vanished",
  quote_exact: "A passage that vanished on re-ingest",
  status: "orphaned",
};

const note = {
  id: "n1",
  title: "Ada's algorithm",
  body_markdown: "A note about [[Babbage]].",
  tags: ["history"],
  anchors: [liveAnchor, orphanAnchor],
  created_at: "now",
  updated_at: "now",
};

const backlinks = [{ note_id: "n2", title: "Babbage engine" }];

const NOTE_URL = "/api/notes/n1";
const BACKLINKS_URL = "/api/notes/n1/backlinks";

function loadHandlers(extra: Record<string, Handler> = {}) {
  return {
    "GET /api/auth/me": () => authedMe.clone(),
    [`GET ${NOTE_URL}`]: () => jsonResponse(200, note),
    [`GET ${BACKLINKS_URL}`]: () => jsonResponse(200, backlinks),
    ...extra,
  };
}

afterEach(() => {
  cleanup();
  nav.push.mockClear();
  vi.restoreAllMocks();
});

describe("NoteDetailScreen (NF-13/14)", () => {
  it("loads the note, its anchored passages, and its backlinks", async () => {
    vi.stubGlobal("fetch", routedFetch(loadHandlers()));

    render(<NoteDetailScreen noteId="n1" />);

    // Title and body hydrate the editor.
    expect(
      ((await screen.findByLabelText("Title")) as HTMLInputElement).value,
    ).toBe("Ada's algorithm");
    expect((screen.getByLabelText("Body") as HTMLTextAreaElement).value).toBe(
      "A note about [[Babbage]].",
    );

    // A live anchor offers a jump-back into the reader at its encoded anchor.
    const jump = screen.getByRole("link", { name: "Jump to passage" });
    expect(jump.getAttribute("href")).toBe(
      "/sources/s1/read?anchor=chapter-1.xhtml%23core-idea",
    );

    // The orphaned anchor keeps its quote and a distinct badge, and offers no jump.
    expect(screen.getByText("A passage that vanished on re-ingest")).toBeTruthy();
    expect(screen.getByTestId("anchor-status-orphaned")).toBeTruthy();
    expect(screen.getAllByRole("link", { name: "Jump to passage" }).length).toBe(1);

    // A backlink links to its note.
    expect(
      screen.getByRole("link", { name: "Babbage engine" }).getAttribute("href"),
    ).toBe("/notes/n2");
  });

  it("enables Save only while dirty and persists the edit", async () => {
    let patchBody: unknown = null;
    vi.stubGlobal(
      "fetch",
      routedFetch(
        loadHandlers({
          [`PATCH ${NOTE_URL}`]: (init) => {
            patchBody = JSON.parse(init.body as string);
            return jsonResponse(200, { ...note, body_markdown: "Edited body." });
          },
        }),
      ),
    );

    render(<NoteDetailScreen noteId="n1" />);

    const save = (await screen.findByRole("button", {
      name: "Save",
    })) as HTMLButtonElement;
    // Nothing changed yet → Save is disabled.
    expect(save.disabled).toBe(true);

    fireEvent.change(screen.getByLabelText("Body"), {
      target: { value: "Edited body." },
    });
    expect(save.disabled).toBe(false);

    fireEvent.click(save);

    await waitFor(() => expect(patchBody).not.toBeNull());
    expect(patchBody).toEqual({
      title: "Ada's algorithm",
      body_markdown: "Edited body.",
      tags: ["history"],
    });
    // Re-baselined after the save → Save disabled again.
    await waitFor(() => expect(save.disabled).toBe(true));
  });

  it("offers the note→review promotion affordance once the note has loaded", async () => {
    // The panel is wired in but idle: it must not fetch on mount (the routed fetch
    // throws on any unregistered call), so a stray suggest here would fail the test.
    vi.stubGlobal("fetch", routedFetch(loadHandlers()));

    render(<NoteDetailScreen noteId="n1" />);

    expect(
      await screen.findByRole("button", { name: "Add to review" }),
    ).toBeTruthy();
  });

  it("toggles a Markdown preview of the body", async () => {
    vi.stubGlobal("fetch", routedFetch(loadHandlers()));

    render(<NoteDetailScreen noteId="n1" />);

    fireEvent.click(await screen.findByRole("button", { name: "Preview" }));

    const preview = await screen.findByTestId("note-preview");
    expect(preview.textContent).toContain("A note about");
    // The textarea is swapped out while previewing.
    expect(screen.queryByLabelText("Body")).toBeNull();
  });

  it("flags an over-cap save without persisting a broken state", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch(
        loadHandlers({
          [`PATCH ${NOTE_URL}`]: () =>
            jsonResponse(422, { detail: "Note body is too long." }),
        }),
      ),
    );

    render(<NoteDetailScreen noteId="n1" />);

    fireEvent.change(await screen.findByLabelText("Body"), {
      target: { value: "way too long" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toMatch(/too long to save/i);
  });

  it("deletes the note behind a confirm and returns to the list", async () => {
    vi.stubGlobal(
      "fetch",
      routedFetch(
        loadHandlers({
          [`DELETE ${NOTE_URL}`]: () => new Response(null, { status: 204 }),
        }),
      ),
    );

    render(<NoteDetailScreen noteId="n1" />);

    fireEvent.click(await screen.findByRole("button", { name: "Delete" }));
    // The destructive action is confirm-gated.
    fireEvent.click(screen.getByRole("button", { name: "Confirm delete" }));

    await waitFor(() => expect(nav.push).toHaveBeenCalledWith("/notes"));
  });
});

describe("NoteDetailScreen in pt-BR", () => {
  /** Hold a response until the test releases it, to see the in-flight state. */
  function deferred() {
    let release: (response: Response) => void = () => {};
    const promise = new Promise<Response>((resolve) => {
      release = resolve;
    });
    return { promise, release };
  }

  const NOTE_NAMESPACES = [
    "notes.detail",
    "notes.suggestions",
    "notes.anchorStatus",
    "errors.operation.notesGet",
    "errors.operation.notesDelete",
    "errors.operation.cardsSuggestNote",
    "common",
  ];

  const body = () => document.body.textContent ?? "";

  // The learner's own text in their language, so the copy probe reads only UI.
  const notaPt = {
    ...note,
    title: "O algoritmo de Ada",
    body_markdown: "Uma anotação sobre [[Babbage]].",
  };

  const SUGGEST_URL = "/api/notes/n1/cards/suggest";
  const CARDS_URL = "/api/notes/n1/cards";
  const suggestion = {
    item_type: "free_recall",
    question: "O que agenda as revisões?",
    answer: "A repetição espaçada",
    anchor_quote: "A repetição espaçada agenda as revisões",
  };
  const card = {
    id: "nc1",
    source_id: null,
    origin: "note",
    note_anchor_id: null,
    item_type: "free_recall",
    question: suggestion.question,
    answer: suggestion.answer,
    citation: { section_path: [], anchor: "", source_excerpt: "x" },
    status: "active",
    created_at: "now",
    updated_at: "now",
  };

  it("editor, anchors, backlinks and add-to-review: renders in pt-BR", async () => {
    setTestLocale("pt-BR");
    const suggest = deferred();
    let accepts = 0;
    const remove = deferred();
    vi.stubGlobal(
      "fetch",
      routedFetch(
        loadHandlers({
          [`GET ${NOTE_URL}`]: () => jsonResponse(200, notaPt),
          [`POST ${SUGGEST_URL}`]: () => suggest.promise,
          // The first promotion creates the card; the second finds it already there.
          [`POST ${CARDS_URL}`]: () =>
            jsonResponse(accepts++ === 0 ? 201 : 200, card),
          [`DELETE ${NOTE_URL}`]: () => remove.promise,
        }),
      ),
    );
    render(<NoteDetailScreen noteId="n1" />);

    expect(await screen.findByLabelText("Título")).toBeTruthy();
    expect(screen.getByRole("region", { name: "nota" })).toBeTruthy();
    expect(screen.getByLabelText("Texto")).toBeTruthy();
    expect(screen.getByLabelText("Etiquetas")).toBeTruthy();
    expect(
      screen.getByPlaceholderText("etiquetas, separadas, por vírgula"),
    ).toBeTruthy();
    expect(screen.getByRole("button", { name: "Salvar" })).toBeTruthy();
    for (const heading of ["Revisão", "Trechos ancorados", "Referências"]) {
      expect(screen.getByText(heading)).toBeTruthy();
    }
    expect(screen.getByTestId("anchor-status-active").textContent).toBe("ativo");
    expect(screen.getByTestId("anchor-status-orphaned").textContent).toBe(
      "fora do livro",
    );
    expect(body()).toContain("Este trecho não está mais no livro.");
    expect(screen.getByRole("link", { name: "Ir para o trecho" })).toBeTruthy();
    expectNoEnglishCopy(body(), ...NOTE_NAMESPACES);

    fireEvent.click(screen.getByRole("button", { name: "Visualizar" }));
    expect(screen.getByRole("button", { name: "Editar" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Editar" }));

    // Suggest: in flight, then a chip, promoted twice (created, then existing).
    fireEvent.click(screen.getByRole("button", { name: "Adicionar à revisão" }));
    expect(await screen.findByRole("button", { name: "Gerando…" })).toBeTruthy();
    expectNoEnglishCopy(body(), ...NOTE_NAMESPACES);
    await act(async () => {
      suggest.release(jsonResponse(200, { suggestions: [suggestion, suggestion] }));
    });
    expect(await screen.findAllByRole("button", { name: "Descartar" })).toHaveLength(2);
    fireEvent.click(screen.getAllByRole("button", { name: "Aceitar" })[0]);
    expect((await screen.findByTestId("note-card-count")).textContent).toBe(
      "1 cartão desta nota em revisão",
    );
    fireEvent.click(screen.getAllByRole("button", { name: "Aceitar" })[0]);
    expect(
      await screen.findByText(
        "Esse cartão já está em revisão — promover o mesmo texto de novo nunca o duplica.",
      ),
    ).toBeTruthy();
    expectNoEnglishCopy(body(), ...NOTE_NAMESPACES);

    fireEvent.click(screen.getByRole("button", { name: "Excluir" }));
    expect(screen.getByText("Excluir esta nota?")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancelar" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Confirmar exclusão" }));
    expect(await screen.findByRole("button", { name: "Excluindo…" })).toBeTruthy();
    expectNoEnglishCopy(body(), ...NOTE_NAMESPACES);
    await act(async () => {
      remove.release(jsonResponse(404, { detail: "Not Found" }));
    });
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Não foi possível excluir a nota.",
    );
  });

  it("no anchors, no backlinks, no cards and a failed suggest: renders in pt-BR", async () => {
    setTestLocale("pt-BR");
    let suggests = 0;
    vi.stubGlobal(
      "fetch",
      routedFetch(
        loadHandlers({
          [`GET ${NOTE_URL}`]: () => jsonResponse(200, { ...notaPt, anchors: [] }),
          [`GET ${BACKLINKS_URL}`]: () => jsonResponse(200, []),
          [`POST ${SUGGEST_URL}`]: () =>
            suggests++ === 0
              ? jsonResponse(200, { suggestions: [] })
              : jsonResponse(404, { detail: "Not Found" }),
        }),
      ),
    );
    render(<NoteDetailScreen noteId="n1" />);

    expect(
      await screen.findByText("Nenhum destaque ancorado a esta nota."),
    ).toBeTruthy();
    expect(screen.getByText("Nenhuma nota aponta para cá ainda.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Adicionar à revisão" }));
    expect(
      await screen.findByText("Não foi possível basear nenhum cartão nesta nota."),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Adicionar à revisão" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Não foi possível sugerir cartões para esta nota.",
    );
    expectNoEnglishCopy(body(), ...NOTE_NAMESPACES);
  });

  it("loading, failed load, save errors and signed-out: renders in pt-BR", async () => {
    setTestLocale("pt-BR");
    const auth = deferred();
    const load = deferred();
    const save = deferred();
    let patches = 0;
    vi.stubGlobal(
      "fetch",
      routedFetch(
        loadHandlers({
          "GET /api/auth/me": () => auth.promise,
          [`GET ${NOTE_URL}`]: () => load.promise,
          [`PATCH ${NOTE_URL}`]: () =>
            patches++ === 0
              ? jsonResponse(422, { detail: "Note body is too long." })
              : save.promise,
        }),
      ),
    );
    render(<NoteDetailScreen noteId="n1" />);

    expect(screen.getByText("Carregando…")).toBeTruthy();
    await act(async () => {
      auth.release(authedMe.clone());
    });
    expect(await screen.findByText("Carregando a nota…")).toBeTruthy();
    expectNoEnglishCopy(body(), ...NOTE_NAMESPACES);
    await act(async () => {
      load.release(jsonResponse(200, notaPt));
    });

    fireEvent.change(await screen.findByLabelText("Texto"), {
      target: { value: "longo demais" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Esta nota é longa demais para ser salva.",
    );
    fireEvent.click(screen.getByRole("button", { name: "Salvar" }));
    expect(await screen.findByRole("button", { name: "Salvando…" })).toBeTruthy();
    expectNoEnglishCopy(body(), ...NOTE_NAMESPACES);
    await act(async () => {
      save.release(jsonResponse(200, { ...notaPt, body_markdown: "longo demais" }));
    });
    cleanup();

    vi.stubGlobal(
      "fetch",
      routedFetch(
        loadHandlers({
          [`GET ${NOTE_URL}`]: () => jsonResponse(404, { detail: "Not Found" }),
        }),
      ),
    );
    render(<NoteDetailScreen noteId="n1" />);
    expect((await screen.findByRole("alert")).textContent).toBe(
      "Não foi possível carregar essa nota.",
    );
    expect(screen.getByRole("link", { name: "Voltar para suas notas" })).toBeTruthy();
    expectNoEnglishCopy(body(), ...NOTE_NAMESPACES);
    cleanup();

    vi.stubGlobal(
      "fetch",
      routedFetch({ "GET /api/auth/me": () => new Response(null, { status: 401 }) }),
    );
    render(<NoteDetailScreen noteId="n1" />);
    expect(await screen.findByText("Você não está conectado.")).toBeTruthy();
  });

  it("user text is never translated", async () => {
    setTestLocale("pt-BR");
    vi.stubGlobal("fetch", routedFetch(loadHandlers()));
    render(<NoteDetailScreen noteId="n1" />);

    // The note is the learner's own words: English stays English in pt-BR.
    expect(
      ((await screen.findByLabelText("Título")) as HTMLInputElement).value,
    ).toBe("Ada's algorithm");
    expect((screen.getByLabelText("Texto") as HTMLTextAreaElement).value).toBe(
      "A note about [[Babbage]].",
    );
    expect((screen.getByLabelText("Etiquetas") as HTMLInputElement).value).toBe(
      "history",
    );
    expect(body()).toContain("Ada wrote the first algorithm");
    expect(body()).toContain("A passage that vanished on re-ingest");
    expect(screen.getByRole("link", { name: "Babbage engine" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Visualizar" }));
    await waitFor(() =>
      expect(screen.getByTestId("note-preview").textContent).toContain(
        "A note about",
      ),
    );
  });
});
