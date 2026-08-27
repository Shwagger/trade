import type { Marketplace } from "./types";

// ---------------------------------------------------------------------
// PROVISOIRE — PHASE 1 SEULEMENT.
// En phase 3 ce fichier disparaît au profit de lib/affiliates.ts et tous
// les liens passent par /go/[suggestionId] (enregistrement du clic puis
// 302). Ici on se contente d'une URL de recherche publique, sans tag,
// juste pour que le parcours soit cliquable de bout en bout.
// ---------------------------------------------------------------------

const SEARCH_URL: Record<Marketplace, (q: string) => string> = {
  amazon_br: (q) => `https://www.amazon.com.br/s?k=${q}`,
  mercado_livre: (q) => `https://lista.mercadolivre.com.br/${q}`,
  magalu: (q) => `https://www.magazineluiza.com.br/busca/${q}/`,
  shopee: (q) => `https://shopee.com.br/search?keyword=${q}`,
};

export function searchUrl(marketplace: Marketplace, searchQuery: string): string {
  const encoded = encodeURIComponent(searchQuery.trim());
  return SEARCH_URL[marketplace](encoded);
}
