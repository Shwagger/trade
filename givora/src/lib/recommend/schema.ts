import { z } from "zod";

// Le schéma sert deux fois : il contraint la sortie du modèle
// (structured outputs) ET il revalide ce qui revient. Le modèle peut
// respecter le JSON sans respecter les règles produit — c'est ce que
// `checkRules` attrape.

export const MARKETPLACES = ["amazon_br", "mercado_livre", "magalu", "shopee"] as const;

export const SuggestionSchema = z.object({
  title: z.string().min(3).max(90),
  reason: z.string().min(20).max(240),
  category: z.string().min(3).max(30),
  search_query: z.string().min(3).max(60),
  price_range: z.string().min(3).max(40),
  marketplace: z.enum(MARKETPLACES),
});

export const RecommendationSchema = z.object({
  suggestions: z.array(SuggestionSchema).length(3),
});

export type ModelSuggestion = z.infer<typeof SuggestionSchema>;

// Formules de pub interdites par le prompt. On revérifie côté serveur :
// une consigne dans un prompt n'est pas une garantie.
const BANNED = [
  "presente perfeito",
  "vai amar",
  "vai adorar",
  "com certeza",
  "imperdível",
  "surpreenda",
  "não tem erro",
  "sem dúvida",
];

/**
 * Règles produit que le JSON valide peut quand même violer.
 * Renvoie la liste des problèmes ; vide = bon à servir.
 */
export function checkRules(suggestions: ModelSuggestion[]): string[] {
  const problems: string[] = [];

  const categories = new Set(suggestions.map((s) => s.category.trim().toLowerCase()));
  if (categories.size < 3) problems.push("categorias repetidas");

  for (const s of suggestions) {
    const reason = s.reason.toLowerCase();

    const banned = BANNED.find((b) => reason.includes(b));
    if (banned) problems.push(`linguagem de propaganda: "${banned}"`);

    // « une seule phrase » : on tolère un point final, pas trois phrases.
    const sentences = s.reason.split(/[.!?]+\s/).filter((p) => p.trim().length > 0);
    if (sentences.length > 1) problems.push(`reason com mais de uma frase: "${s.title}"`);

    const words = s.search_query.trim().split(/\s+/).length;
    if (words < 2 || words > 5) problems.push(`search_query com ${words} palavra(s): "${s.search_query}"`);
  }

  return problems;
}

/**
 * Le prix annoncé doit tenir dans le budget. On lit les nombres du
 * price_range plutôt que de faire confiance au modèle.
 */
export function withinBudget(priceRange: string, min: number, max: number | null): boolean {
  if (max === null) return true;
  const numbers = priceRange.match(/\d+/g)?.map(Number) ?? [];
  if (numbers.length === 0) return true; // rien à vérifier, on laisse passer
  return Math.max(...numbers) <= max * 1.05 && Math.min(...numbers) >= min * 0.5;
}
