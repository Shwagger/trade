// Types partagés client/serveur. Ils suivent 1:1 le schéma SQL de
// supabase/migrations/0001_init.sql.

export type Marketplace = "amazon_br" | "mercado_livre" | "magalu" | "shopee";

export type Suggestion = {
  id: string;
  request_id: string;
  title: string;
  reason: string;
  category: string;
  search_query: string;
  price_range: string;
  marketplace: Marketplace;
  position: number;
  /** Pictogramme de la carte. Voir src/lib/visuals.ts. */
  glyph?: string;
};

export type GiftRequest = {
  id: string;
  recipient_id: string | null;
  occasion: string;
  budget_min: number;
  budget_max: number | null;
  raw_input: string | null;
  /** Jours avant l'événement. null = sans pressa. */
  deadline_days: number | null;
  shared_at: string | null;
  created_at: string;
};

export type Recipient = {
  id: string;
  nickname: string | null;
  relation: string;
  age_range: string | null;
  interests: string[];
  notes: string | null;
};

// Ce que le formulaire envoie à POST /api/request.
export type RequestPayload = {
  relation: string;
  ageRange: string;
  interests: string[];
  freeText: string;
  occasion: string;
  budgetId: string;
  deadlineId: string;
};

/** Décompte des votes du groupe, par suggestion. */
export type VoteTally = {
  suggestion_id: string;
  up: number;
  down: number;
  /** Le vote de CE visiteur, s'il en a déjà donné un. */
  mine: -1 | 1 | null;
};
