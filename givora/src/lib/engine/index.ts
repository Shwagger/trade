import type { SuggestionDraft } from "../store";
import { CATALOG, type Archetype } from "./catalog";
import { extractSignals } from "./lexicon";
import { buildReason } from "./reasons";
import { pickThree, scoreArchetype, type ScoreInput } from "./score";

// =====================================================================
// LE MOTEUR. Pas d'appel réseau, pas de clé API, pas de coût par
// session : quelques millisecondes de CPU. La commission d'affiliation
// est donc une marge de 100 %, et on peut servir autant de trafic qu'on
// en trouve sans que la facture bouge.
//
// Trois autres conséquences qui comptent autant :
//   - la réponse est instantanée, donc le parcours tient vraiment en
//     moins de 30 secondes ;
//   - le résultat est reproductible à partir de la graine, donc quand une
//     suggestion est mauvaise on peut rejouer exactement le cas ;
//   - rien ne peut « halluciner » un produit qui n'existe pas.
// =====================================================================

export type EngineInput = {
  relation: string;
  ageRange: string | null;
  interests: string[];
  freeText: string | null;
  occasion: string;
  budgetMin: number;
  budgetMax: number | null;
  deadlineDays: number | null;
  feedback?: string | null;
  avoidTitles?: string[];
  rejectedTitles?: string[];
  /** Rend le tirage reproductible. En prod : l'id de la demande. */
  seed: string;
};

/**
 * Fourchette de prix affichée. Elle doit rester dans le budget annoncé,
 * sinon la promesse est cassée dès la première carte.
 */
function priceRange(a: Archetype, min: number, max: number | null): string {
  // La fourchette part TOUJOURS du prix réel de l'article. On la resserre
  // au budget, on ne la gonfle jamais pour qu'elle y ressemble — c'est ce
  // qui produirait un prix affiché que l'article n'a pas.
  const lo = round5(Math.min(Math.max(a.floor, min), a.typical));
  // On borne aussi l'écart : « R$ 500 - R$ 1285 » est honnête mais
  // illisible. Au-delà du double du plancher, la fourchette n'aide plus.
  const hi = Math.min(Math.round(a.typical * 1.35), Math.round(lo * 2.2));

  // Le plafond du budget est une promesse : la fourchette affichée ne le
  // dépasse jamais, même de cinq reais. Si l'espace restant est trop
  // mince pour une fourchette lisible, on annonce un prix unique.
  const capped = max === null ? round5(hi) : Math.min(round5(hi), max);

  if (capped <= lo + 5) return `Cerca de R$ ${lo}`;
  return `R$ ${lo} - R$ ${capped}`;
}

const round5 = (n: number) => Math.round(n / 5) * 5;

export function recommend(input: EngineInput): SuggestionDraft[] {
  // Le feedback du « refinar » est du texte libre lui aussi : il entre
  // dans le même extracteur, donc « prefiro algo para a casa » ajoute
  // vraiment le signal « casa ».
  const signals = extractSignals(
    [input.freeText, input.feedback].filter(Boolean).join(" "),
    input.interests,
  );

  const scoreInput: ScoreInput = {
    signals,
    relation: input.relation,
    ageRange: input.ageRange,
    occasion: input.occasion,
    budgetMin: input.budgetMin,
    budgetMax: input.budgetMax,
    deadlineDays: input.deadlineDays,
    avoidTitles: new Set(input.avoidTitles ?? []),
    rejected: new Set(input.rejectedTitles ?? []),
  };

  // La graine bouge avec le feedback : sans ça, « refinar » sans changer
  // d'avis renverrait exactement le même trio.
  const seed = input.seed + (input.feedback ? `|${input.feedback}` : "");

  const scored = CATALOG
    .map((a) => scoreArchetype(a, scoreInput, seed))
    .filter((s): s is NonNullable<typeof s> => s !== null);

  const urgent = input.deadlineDays !== null && input.deadlineDays <= 2;

  return pickThree(scored).map((s, i) => ({
    title: s.archetype.title,
    reason: buildReason({ archetype: s.archetype, matched: s.matched, position: i, urgent }),
    category: s.archetype.category,
    search_query: s.archetype.query,
    price_range: priceRange(s.archetype, input.budgetMin, input.budgetMax),
    marketplace: s.archetype.store,
    position: i + 1,
    glyph: s.archetype.glyph,
  }));
}

/** Le détail du calcul, pour comprendre une suggestion bizarre. */
export function explain(input: EngineInput) {
  const signals = extractSignals(
    [input.freeText, input.feedback].filter(Boolean).join(" "),
    input.interests,
  );
  const scoreInput: ScoreInput = {
    signals, relation: input.relation, ageRange: input.ageRange, occasion: input.occasion,
    budgetMin: input.budgetMin, budgetMax: input.budgetMax, deadlineDays: input.deadlineDays,
    avoidTitles: new Set(input.avoidTitles ?? []), rejected: new Set(input.rejectedTitles ?? []),
  };
  const scored = CATALOG
    .map((a) => scoreArchetype(a, scoreInput, input.seed))
    .filter((s): s is NonNullable<typeof s> => s !== null)
    .sort((a, b) => b.score - a.score);

  return { signals, candidates: scored.length, top: scored.slice(0, 8) };
}
