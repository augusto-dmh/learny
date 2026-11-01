/**
 * The one shape a failed browser request takes, and the catalog copy it maps to.
 *
 * Every request client under `app/lib` throws an `ApiError` (or a subclass that
 * adds a `kind` its callers branch on) for a non-OK response. It carries three
 * facts and no sentence:
 *
 * - `operation` — what the learner was trying to do, as a key of
 *   `errors.operation` in the catalogs (`sourcesList`, `notesSave`, …). It is
 *   also the error's `message`, so a stray `String(err)` in a log reads as a
 *   key, never as English copy.
 * - `status` — the HTTP status, or `"network"` when the server was unreachable.
 * - `detail` — the backend's `detail`, kept as data for logs and debugging. It is
 *   never shown: the backend explains failures in English, and showing that text
 *   would leak English into every other locale.
 * - `code` — the backend's machine code beside the `detail` on the typed
 *   refusals (the learner-side BYOK rails). Also data, never shown; a refusal
 *   code maps to its own catalog copy below.
 *
 * What the learner reads is chosen by {@link errorMessageKey}: a status class
 * that means the same thing whatever was being done (an expired session, rate
 * limiting, a server fault, no connection) wins over the operation; anything
 * else reads as the operation's own failure copy. Components resolve the key
 * through `useErrorMessage` (`app/components/use-error-message.ts`).
 */
import type en from "@/messages/en.json";

type ErrorCatalog = (typeof en)["errors"];

/** What the learner was doing when the request failed: a key of `errors.operation`. */
export type ApiOperation = keyof ErrorCatalog["operation"];

/** The HTTP status of the failed response, or `"network"` for no response at all. */
export type ApiErrorStatus = number | "network";

/** A status class whose copy is shared by every operation: a key of `errors.status`. */
export type StatusClass = keyof ErrorCatalog["status"];

/** A key under the `errors` namespace that names one failure sentence. */
export type ErrorMessageKey =
  | "generic"
  | `status.${StatusClass}`
  | `stream.${keyof ErrorCatalog["stream"]}`
  | `operation.${ApiOperation}`;

/**
 * What a surface shows when the value it caught is not an `ApiError` (a thrown
 * `TypeError`, an SDK error): an operation, or any failure key.
 */
export type ErrorFallback = ApiOperation | ErrorMessageKey;

/** A failed request: the operation, the status, the backend detail and the machine code. */
export class ApiError extends Error {
  readonly operation: ApiOperation;
  readonly status: ApiErrorStatus;
  readonly detail: string | null;
  /**
   * The backend's machine code beside the `detail` (`{"detail", "code"}`), or
   * `null` when the body carries none. Like `detail` it is data, never copy:
   * the learner reads catalog text keyed off it.
   */
  readonly code: string | null;

  constructor(
    operation: ApiOperation,
    status: ApiErrorStatus,
    detail: string | null = null,
    code: string | null = null,
  ) {
    super(operation);
    this.name = "ApiError";
    this.operation = operation;
    this.status = status;
    this.detail = detail;
    this.code = code;
  }
}

/**
 * The backend `detail` of a non-OK response, as a string for logs, or null when
 * the body is not JSON or carries none. A FastAPI validation error's list-shaped
 * detail is serialized rather than dropped. Never throws.
 */
export async function readDetail(res: Response): Promise<string | null> {
  return (await readErrorBody(res)).detail;
}

/**
 * The backend body of a non-OK response, read as data: the `detail` string and
 * the machine `code` beside it (`{"detail", "code"}` — the typed refusals).
 * Either is null when the body is not JSON or carries none; a list-shaped
 * validation detail is serialized rather than dropped. Never throws.
 */
export async function readErrorBody(
  res: Response,
): Promise<{ detail: string | null; code: string | null }> {
  try {
    const body = (await res.json()) as { detail?: unknown; code?: unknown } | null;
    const detail = body?.detail;
    return {
      detail:
        detail === undefined || detail === null
          ? null
          : typeof detail === "string"
            ? detail
            : JSON.stringify(detail),
      code: typeof body?.code === "string" ? body.code : null,
    };
  } catch {
    return { detail: null, code: null };
  }
}

/** Build the `ApiError` for a non-OK response to `operation`. */
export async function apiErrorFrom(res: Response, operation: ApiOperation): Promise<ApiError> {
  const { detail, code } = await readErrorBody(res);
  return new ApiError(operation, res.status, detail, code);
}

/**
 * Statuses an operation expects as its own outcome rather than as the shared
 * status class: a `401` from the login form means the credentials were wrong,
 * not that a session expired.
 */
const OWN_STATUSES: Partial<Record<ApiOperation, readonly number[]>> = {
  authLogin: [401],
};

/** The chat operations, whose pre-stream guards have status-specific copy. */
const CHAT_OPERATIONS: ReadonlySet<ApiOperation> = new Set<ApiOperation>([
  "conversationsStart",
  "chatTurn",
]);

/** The chat copy for each status a pre-stream guard returns. */
const CHAT_STATUS_COPY: Readonly<Record<number, ErrorMessageKey>> = {
  403: "stream.forbidden",
  404: "stream.notFound",
  409: "stream.notReady",
  422: "stream.unprocessable",
};

/** The shared status class a status falls in, or null when the operation's copy applies. */
export function statusClassOf(status: ApiErrorStatus): StatusClass | null {
  if (status === "network") return "network";
  if (status === 401) return "unauthorized";
  if (status === 429) return "rateLimited";
  if (status >= 500) return "server";
  return null;
}

/**
 * The backend's machine refusal codes (`{"detail", "code"}`) that carry their
 * own catalog copy, winning over the status classes: a learner-side BYOK rail
 * pausing their own key is a different fact from the shared "too many
 * requests", whatever surface it refused. Only these two codes exist today;
 * an unrecognized code falls through to the ordinary mapping.
 */
const TYPED_REFUSALS: Readonly<Record<string, ErrorMessageKey>> = {
  byok_budget: "stream.byokBudget",
  byok_corpus_limit: "stream.byokCorpusLimit",
};

function fallbackKey(fallback: ErrorFallback): ErrorMessageKey {
  return fallback === "generic" || fallback.includes(".")
    ? (fallback as ErrorMessageKey)
    : `operation.${fallback as ApiOperation}`;
}

/**
 * The `errors.*` key a caught value reads as. An `ApiError` maps by a typed
 * refusal code first, then by status class, then by the chat guards' status
 * copy, then by its operation; any other value reads as `fallback`. The
 * backend `detail` never takes part.
 */
export function errorMessageKey(error: unknown, fallback: ErrorFallback): ErrorMessageKey {
  if (!(error instanceof ApiError)) {
    return fallbackKey(fallback);
  }
  const typed = error.code !== null ? TYPED_REFUSALS[error.code] : undefined;
  if (typed) {
    return typed;
  }
  const { operation, status } = error;
  if (typeof status === "number" && OWN_STATUSES[operation]?.includes(status)) {
    return `operation.${operation}`;
  }
  const statusClass = statusClassOf(status);
  if (statusClass) {
    return `status.${statusClass}`;
  }
  if (CHAT_OPERATIONS.has(operation) && typeof status === "number") {
    const chatCopy = CHAT_STATUS_COPY[status];
    if (chatCopy) return chatCopy;
  }
  return `operation.${operation}`;
}
