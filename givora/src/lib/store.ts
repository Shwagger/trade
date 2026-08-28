import { randomUUID } from "node:crypto";
import { getSupabase } from "./supabase";
import type { GiftRequest, Recipient, Suggestion, VoteTally } from "./types";

// ---------------------------------------------------------------------
// Couche d'accès aux données. Une seule porte d'entrée pour le reste de
// l'app : si Supabase est configuré on écrit dans Postgres, sinon on
// retombe sur un store en mémoire pour que `npm run dev` marche tout de
// suite, sans credentials. Le fallback est volontairement bête et
// s'efface à chaque redémarrage — il n'est là que pour le dev local.
// ---------------------------------------------------------------------

const SUGGESTION_COLUMNS =
  "id, request_id, title, reason, category, search_query, price_range, marketplace, position";

const REQUEST_COLUMNS =
  "id, recipient_id, occasion, budget_min, budget_max, raw_input, deadline_days, shared_at, created_at";

type MemoryDb = {
  recipients: Map<string, Recipient>;
  requests: Map<string, GiftRequest>;
  suggestions: Map<string, Suggestion[]>; // request_id -> suggestions
  votes: Map<string, { suggestionId: string; requestId: string; sessionId: string; value: -1 | 1 }>;
  clicks: { id: string; suggestion_id: string; clicked_at: string; session_id: string | null }[];
  sessions: Map<string, { session_id: string; first_seen: string; source: Record<string, string>; pages_viewed: number }>;
};

// globalThis : Next recharge les modules à chaud en dev, on ne veut pas
// perdre les données entre deux compilations.
const g = globalThis as unknown as { __givoraDb?: MemoryDb };
const memory: MemoryDb =
  g.__givoraDb ??
  (g.__givoraDb = {
    recipients: new Map(),
    requests: new Map(),
    suggestions: new Map(),
    votes: new Map(),
    clicks: [],
    sessions: new Map(),
  });

export function usingMemoryStore(): boolean {
  return getSupabase() === null;
}

// --- recipients ------------------------------------------------------

export async function createRecipient(input: {
  nickname: string | null;
  relation: string;
  ageRange: string | null;
  interests: string[];
  notes: string | null;
}): Promise<Recipient> {
  const row: Recipient = {
    id: randomUUID(),
    nickname: input.nickname,
    relation: input.relation,
    age_range: input.ageRange,
    interests: input.interests,
    notes: input.notes,
  };

  const db = getSupabase();
  if (!db) {
    memory.recipients.set(row.id, row);
    return row;
  }

  const { data, error } = await db
    .from("recipients")
    .insert({
      nickname: row.nickname,
      relation: row.relation,
      age_range: row.age_range,
      interests: row.interests,
      notes: row.notes,
    })
    .select("id, nickname, relation, age_range, interests, notes")
    .single();

  if (error) throw new Error(`recipients insert: ${error.message}`);
  return data as Recipient;
}

// --- requests --------------------------------------------------------

export async function createRequest(input: {
  /** Id dérivé du jeton : le même lien partagé = la même ligne. */
  id?: string;
  recipientId: string | null;
  occasion: string;
  budgetMin: number;
  budgetMax: number | null;
  rawInput: string | null;
  deadlineDays: number | null;
}): Promise<GiftRequest> {
  const row: GiftRequest = {
    id: input.id ?? randomUUID(),
    recipient_id: input.recipientId,
    occasion: input.occasion,
    budget_min: input.budgetMin,
    budget_max: input.budgetMax,
    raw_input: input.rawInput,
    deadline_days: input.deadlineDays,
    shared_at: null,
    created_at: new Date().toISOString(),
  };

  const db = getSupabase();
  if (!db) {
    memory.requests.set(row.id, row);
    return row;
  }

  // upsert : deux personnes qui ouvrent le même lien partagé ne créent
  // pas deux demandes, elles touchent la même ligne.
  const { data, error } = await db
    .from("requests")
    .upsert({
      id: row.id,
      recipient_id: row.recipient_id,
      occasion: row.occasion,
      budget_min: row.budget_min,
      budget_max: row.budget_max,
      raw_input: row.raw_input,
      deadline_days: row.deadline_days,
    })
    .select(REQUEST_COLUMNS)
    .single();

  if (error) throw new Error(`requests insert: ${error.message}`);
  return data as GiftRequest;
}

export async function getRequest(id: string): Promise<GiftRequest | null> {
  const db = getSupabase();
  if (!db) return memory.requests.get(id) ?? null;

  const { data, error } = await db
    .from("requests")
    .select(REQUEST_COLUMNS)
    .eq("id", id)
    .maybeSingle();

  if (error) throw new Error(`requests select: ${error.message}`);
  return (data as GiftRequest | null) ?? null;
}

export async function getRecipient(id: string): Promise<Recipient | null> {
  const db = getSupabase();
  if (!db) return memory.recipients.get(id) ?? null;

  const { data, error } = await db
    .from("recipients")
    .select("id, nickname, relation, age_range, interests, notes")
    .eq("id", id)
    .maybeSingle();

  if (error) throw new Error(`recipients select: ${error.message}`);
  return (data as Recipient | null) ?? null;
}

// --- suggestions -----------------------------------------------------

export type SuggestionDraft = Omit<Suggestion, "id" | "request_id">;

export async function replaceSuggestions(
  requestId: string,
  drafts: SuggestionDraft[],
): Promise<Suggestion[]> {
  const db = getSupabase();

  if (!db) {
    const rows = drafts.map((d) => ({ ...d, id: randomUUID(), request_id: requestId }));
    memory.suggestions.set(requestId, rows);
    return rows;
  }

  // "refinar" rejoue le moteur sur la même request : on écrase l'ancien
  // trio plutôt que d'empiler (la contrainte unique(request_id, position)
  // l'interdirait de toute façon).
  const del = await db.from("suggestions").delete().eq("request_id", requestId);
  if (del.error) throw new Error(`suggestions delete: ${del.error.message}`);

  const { data, error } = await db
    .from("suggestions")
    .insert(drafts.map((d) => ({ ...d, request_id: requestId })))
    .select(SUGGESTION_COLUMNS)
    .order("position");

  if (error) throw new Error(`suggestions insert: ${error.message}`);
  return data as Suggestion[];
}

export async function getSuggestions(requestId: string): Promise<Suggestion[]> {
  const db = getSupabase();
  if (!db) return memory.suggestions.get(requestId) ?? [];

  const { data, error } = await db
    .from("suggestions")
    .select(SUGGESTION_COLUMNS)
    .eq("request_id", requestId)
    .order("position");

  if (error) throw new Error(`suggestions select: ${error.message}`);
  return (data as Suggestion[]) ?? [];
}

// --- votes -----------------------------------------------------------
// Le lien /resultado/[id] partagé dans le groupe WhatsApp devient un
// sondage : chacun réagit aux trois cartes. Un avis par personne et par
// carte — revoter écrase, ça ne s'empile pas.

export async function castVote(input: {
  suggestionId: string;
  requestId: string;
  sessionId: string;
  value: -1 | 1;
}): Promise<void> {
  const db = getSupabase();

  if (!db) {
    memory.votes.set(`${input.suggestionId}:${input.sessionId}`, {
      suggestionId: input.suggestionId,
      requestId: input.requestId,
      sessionId: input.sessionId,
      value: input.value,
    });
    return;
  }

  const { error } = await db
    .from("votes")
    .upsert(
      {
        suggestion_id: input.suggestionId,
        request_id: input.requestId,
        session_id: input.sessionId,
        value: input.value,
      },
      { onConflict: "suggestion_id,session_id" },
    );

  if (error) throw new Error(`votes upsert: ${error.message}`);
}

export async function getTallies(requestId: string, sessionId: string): Promise<VoteTally[]> {
  const db = getSupabase();

  const rows = db
    ? await db
        .from("votes")
        .select("suggestion_id, session_id, value")
        .eq("request_id", requestId)
        .then(({ data, error }) => {
          if (error) throw new Error(`votes select: ${error.message}`);
          return (data ?? []) as { suggestion_id: string; session_id: string; value: number }[];
        })
    : [...memory.votes.values()]
        .filter((v) => v.requestId === requestId)
        .map((v) => ({ suggestion_id: v.suggestionId, session_id: v.sessionId, value: v.value }));

  const byId = new Map<string, VoteTally>();
  for (const row of rows) {
    const t = byId.get(row.suggestion_id) ?? {
      suggestion_id: row.suggestion_id,
      up: 0,
      down: 0,
      mine: null,
    };
    if (row.value === 1) t.up += 1;
    else t.down += 1;
    if (row.session_id === sessionId) t.mine = row.value === 1 ? 1 : -1;
    byId.set(row.suggestion_id, t);
  }
  return [...byId.values()];
}

/** Les titres que le groupe a rejetés : ils nourrissent le refinar. */
export async function rejectedTitles(requestId: string): Promise<string[]> {
  const [suggestions, tallies] = await Promise.all([
    getSuggestions(requestId),
    getTallies(requestId, ""),
  ]);
  const down = new Set(tallies.filter((t) => t.down > t.up).map((t) => t.suggestion_id));
  return suggestions.filter((s) => down.has(s.id)).map((s) => s.title);
}

/** Trace l'usage réel du partage WhatsApp : la boucle virale existe ou non. */
export async function markShared(requestId: string): Promise<void> {
  const db = getSupabase();
  if (!db) {
    const r = memory.requests.get(requestId);
    if (r) r.shared_at = new Date().toISOString();
    return;
  }
  const { error } = await db
    .from("requests")
    .update({ shared_at: new Date().toISOString() })
    .eq("id", requestId)
    .is("shared_at", null); // on garde le PREMIER partage, pas le dernier
  if (error) console.error("[store] markShared:", error.message);
}

// --- clicks & sessions -----------------------------------------------
// La métrique n°1 du produit : session -> clic sortant. `clicks` est le
// numérateur, `sessions` le dénominateur. Sans les deux, le taux de clic
// est une opinion.

export async function getSuggestionById(id: string): Promise<Suggestion | null> {
  const db = getSupabase();

  if (!db) {
    for (const list of memory.suggestions.values()) {
      const found = list.find((s) => s.id === id);
      if (found) return found;
    }
    return null;
  }

  const { data, error } = await db
    .from("suggestions")
    .select(SUGGESTION_COLUMNS)
    .eq("id", id)
    .maybeSingle();

  if (error) throw new Error(`suggestions select by id: ${error.message}`);
  return (data as Suggestion | null) ?? null;
}

export async function recordClick(input: {
  suggestionId: string;
  referrer: string | null;
  userAgent: string | null;
  sessionId: string | null;
}): Promise<void> {
  const db = getSupabase();

  if (!db) {
    memory.clicks.push({
      id: randomUUID(),
      suggestion_id: input.suggestionId,
      clicked_at: new Date().toISOString(),
      session_id: input.sessionId,
    });
    return;
  }

  const { error } = await db.from("clicks").insert({
    suggestion_id: input.suggestionId,
    referrer: input.referrer,
    user_agent: input.userAgent,
    session_id: input.sessionId,
  });

  // Un clic non enregistré ne doit JAMAIS empêcher la redirection :
  // on perd une mesure, pas une commission.
  if (error) console.error("[store] recordClick:", error.message);
}

export async function touchSession(input: {
  sessionId: string;
  source: Record<string, string>;
}): Promise<void> {
  const db = getSupabase();

  if (!db) {
    const existing = memory.sessions.get(input.sessionId);
    if (existing) existing.pages_viewed += 1;
    else
      memory.sessions.set(input.sessionId, {
        session_id: input.sessionId,
        first_seen: new Date().toISOString(),
        source: input.source,
        pages_viewed: 1,
      });
    return;
  }

  // On garde first_seen et la source d'ORIGINE : un partage WhatsApp ne
  // doit pas réécrire l'attribution de la campagne qui a amené la personne.
  const { error } = await db.rpc("givora_touch_session", {
    p_session_id: input.sessionId,
    p_source: input.source,
  });

  if (error) console.error("[store] touchSession:", error.message);
}
