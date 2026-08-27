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
};

export type GiftRequest = {
  id: string;
  recipient_id: string | null;
  occasion: string;
  budget_min: number;
  budget_max: number | null;
  raw_input: string | null;
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
};
