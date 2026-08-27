import { randomUUID } from "node:crypto";
import { getSupabase } from "./supabase";
import type { GiftRequest, Recipient, Suggestion } from "./types";

// ---------------------------------------------------------------------
// Couche d'accès aux données. Une seule porte d'entrée pour le reste de
// l'app : si Supabase est configuré on écrit dans Postgres, sinon on
// retombe sur un store en mémoire pour que `npm run dev` marche tout de
// suite, sans credentials. Le fallback est volontairement bête et
// s'efface à chaque redémarrage — il n'est là que pour le dev local.
// ---------------------------------------------------------------------

type MemoryDb = {
  recipients: Map<string, Recipient>;
  requests: Map<string, GiftRequest>;
  suggestions: Map<string, Suggestion[]>; // request_id -> suggestions
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
  recipientId: string | null;
  occasion: string;
  budgetMin: number;
  budgetMax: number | null;
  rawInput: string | null;
}): Promise<GiftRequest> {
  const row: GiftRequest = {
    id: randomUUID(),
    recipient_id: input.recipientId,
    occasion: input.occasion,
    budget_min: input.budgetMin,
    budget_max: input.budgetMax,
    raw_input: input.rawInput,
    created_at: new Date().toISOString(),
  };

  const db = getSupabase();
  if (!db) {
    memory.requests.set(row.id, row);
    return row;
  }

  const { data, error } = await db
    .from("requests")
    .insert({
      recipient_id: row.recipient_id,
      occasion: row.occasion,
      budget_min: row.budget_min,
      budget_max: row.budget_max,
      raw_input: row.raw_input,
    })
    .select("id, recipient_id, occasion, budget_min, budget_max, raw_input, created_at")
    .single();

  if (error) throw new Error(`requests insert: ${error.message}`);
  return data as GiftRequest;
}

export async function getRequest(id: string): Promise<GiftRequest | null> {
  const db = getSupabase();
  if (!db) return memory.requests.get(id) ?? null;

  const { data, error } = await db
    .from("requests")
    .select("id, recipient_id, occasion, budget_min, budget_max, raw_input, created_at")
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
    .select("id, request_id, title, reason, category, search_query, price_range, marketplace, position")
    .order("position");

  if (error) throw new Error(`suggestions insert: ${error.message}`);
  return data as Suggestion[];
}

export async function getSuggestions(requestId: string): Promise<Suggestion[]> {
  const db = getSupabase();
  if (!db) return memory.suggestions.get(requestId) ?? [];

  const { data, error } = await db
    .from("suggestions")
    .select("id, request_id, title, reason, category, search_query, price_range, marketplace, position")
    .eq("request_id", requestId)
    .order("position");

  if (error) throw new Error(`suggestions select: ${error.message}`);
  return (data as Suggestion[]) ?? [];
}
