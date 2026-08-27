import { getSupabase } from "./supabase";
import type { Marketplace } from "./types";

// ---------------------------------------------------------------------
// Les chiffres de /admin. Une seule question compte : sur 100 personnes
// qui arrivent, combien cliquent vers un marchand ? Tout le reste est
// du contexte pour comprendre ce chiffre.
// ---------------------------------------------------------------------

export type AdminStats = {
  since: string;
  sessions: number;
  requests: number;
  clicks: number;
  /** Sessions -> clic sortant. LA métrique. */
  clickRate: number | null;
  /** Combien de demandes ont été partagées sur WhatsApp. */
  shared: number;
  byMarketplace: { marketplace: string; clicks: number }[];
  topSuggestions: { title: string; marketplace: string; clicks: number }[];
  live: boolean;
};

const DAY_MS = 24 * 60 * 60 * 1000;

export async function getAdminStats(days = 1): Promise<AdminStats> {
  const since = new Date(Date.now() - days * DAY_MS).toISOString();
  const db = getSupabase();

  // Sans Supabase il n'y a pas d'historique à montrer : on le dit
  // clairement plutôt que d'afficher des zéros qui ressemblent à une
  // mauvaise nouvelle.
  if (!db) {
    return {
      since, sessions: 0, requests: 0, clicks: 0, clickRate: null,
      shared: 0, byMarketplace: [], topSuggestions: [], live: false,
    };
  }

  const [sessions, requests, shared, clickRows] = await Promise.all([
    db.from("sessions").select("*", { count: "exact", head: true }).gte("first_seen", since),
    db.from("requests").select("*", { count: "exact", head: true }).gte("created_at", since),
    db.from("requests").select("*", { count: "exact", head: true }).gte("created_at", since).not("shared_at", "is", null),
    db
      .from("clicks")
      .select("suggestion_id, suggestions(title, marketplace)")
      .gte("clicked_at", since)
      .limit(5000),
  ]);

  type ClickRow = { suggestions: { title: string; marketplace: Marketplace } | null };
  const rows = (clickRows.data ?? []) as unknown as ClickRow[];

  const perMarketplace = new Map<string, number>();
  const perTitle = new Map<string, { title: string; marketplace: string; clicks: number }>();

  for (const row of rows) {
    if (!row.suggestions) continue;
    const { title, marketplace } = row.suggestions;
    perMarketplace.set(marketplace, (perMarketplace.get(marketplace) ?? 0) + 1);

    const key = `${title}::${marketplace}`;
    const entry = perTitle.get(key) ?? { title, marketplace, clicks: 0 };
    entry.clicks += 1;
    perTitle.set(key, entry);
  }

  const sessionCount = sessions.count ?? 0;
  const clickCount = rows.length;

  return {
    since,
    sessions: sessionCount,
    requests: requests.count ?? 0,
    clicks: clickCount,
    clickRate: sessionCount > 0 ? clickCount / sessionCount : null,
    shared: shared.count ?? 0,
    byMarketplace: [...perMarketplace.entries()]
      .map(([marketplace, clicks]) => ({ marketplace, clicks }))
      .sort((a, b) => b.clicks - a.clicks),
    topSuggestions: [...perTitle.values()].sort((a, b) => b.clicks - a.clicks).slice(0, 10),
    live: true,
  };
}
