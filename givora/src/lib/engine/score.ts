import type { Archetype } from "./catalog";
import type { Signal } from "./lexicon";

// =====================================================================
// Le scoring. Une somme pondérée, volontairement lisible : quand une
// suggestion est mauvaise, on doit pouvoir dire POURQUOI elle a gagné.
// Un modèle noir opaque ne donne pas ça.
// =====================================================================

export type ScoreInput = {
  signals: Signal[];
  relation: string;
  ageRange: string | null;
  occasion: string;
  budgetMin: number;
  budgetMax: number | null;
  deadlineDays: number | null;
  /** Titres déjà proposés : le refinar doit changer de direction. */
  avoidTitles: Set<string>;
  /** Ce que le groupe a descendu dans le vote WhatsApp. */
  rejected: Set<string>;
};

export type Scored = {
  archetype: Archetype;
  score: number;
  matched: Signal | null;
  /** Détail du calcul — c'est ce qui rend le moteur débogable. */
  breakdown: Record<string, number>;
};

const W = {
  interest: 4.0,     // le signal le plus fort : ce qu'elle aime vraiment
  interestExtra: 1.2, // chaque signal supplémentaire compte moins
  relation: 1.5,
  age: 1.2,
  occasion: 1.0,
  budget: 2.5,       // un cadeau hors budget est inutilisable, même parfait
  urgentDigital: 3.0,
  urgentPhysical: -1.5,
  alreadyShown: -12,
  rejected: -8,
  // La personne a donné un signal et cet article ne le porte pas : il
  // passe derrière les articles universels (vale-presente, cesta). Sans
  // ça, quand rien de ce qu'elle aime ne rentre dans le budget, le
  // moteur sort au hasard — d'où la perceuse pour la grand-mère qui fait
  // du crochet.
  horaTema: -2.0,
};

/**
 * L'article est-il crédible dans cette fourchette ? 0 à 1, 0 = exclu.
 *
 * Les deux bornes comptent, pas seulement le plafond. Proposer un kit
 * d'aquarelle à 95 reais à quelqu'un qui a dit « R$ 300 ou mais » oblige
 * à afficher un prix que l'article n'a pas — c'est mentir sur l'étiquette,
 * et la personne s'en aperçoit à la première page marchande.
 */
function budgetFit(a: Archetype, min: number, max: number | null): number {
  // Le haut de la fourchette réaliste de l'article. Au-delà, il n'existe
  // pas à ce prix-là.
  const ceiling = a.typical * 1.4;

  if (ceiling < min) return 0;                    // trop bon marché pour ce budget
  if (max !== null && a.floor > max) return 0;    // trop cher pour ce budget

  if (max === null) return a.typical >= min ? 1 : 0.5;
  if (a.typical >= min && a.typical <= max) return 1;

  // Il déborde d'un côté mais reste atteignable en cherchant : on le
  // garde, on le déclasse.
  return 0.45;
}

/**
 * Bruit déterministe entre 0 et 0,5, dérivé de la graine.
 * Sans lui, deux personnes au profil identique voient exactement la même
 * chose et le refinar ne bouge pas. Avec une graine, c'est reproductible
 * — donc débogable.
 */
export function jitter(seed: string, id: string): number {
  let h = 2166136261;
  const s = seed + "|" + id;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return ((h >>> 0) % 1000) / 2000;
}

export function scoreArchetype(a: Archetype, input: ScoreInput, seed: string): Scored | null {
  // Filtre dur : ce que le budget ne paie pas ne doit jamais s'afficher.
  if (input.budgetMax !== null && a.floor > input.budgetMax) return null;

  const breakdown: Record<string, number> = {};
  let matched: Signal | null = null;

  // --- intérêts ------------------------------------------------------
  const hits = input.signals.filter((s) => a.tags.includes(s.tag));
  if (hits.length > 0) {
    matched = hits[0];
    breakdown.interest = W.interest + (hits.length - 1) * W.interestExtra;
  } else if (input.signals.length > 0 && a.tags.length > 0) {
    breakdown.foraDoTema = W.horaTema;
  }

  // --- affinités ------------------------------------------------------
  if (a.relations?.includes(input.relation)) breakdown.relation = W.relation;
  if (input.ageRange && a.ages?.includes(input.ageRange)) breakdown.age = W.age;
  // Une liste d'âges qui n'inclut pas la personne est disqualifiante :
  // un brinquedo de montar pour une grand-mère, c'est embarrassant.
  if (input.ageRange && a.ages && !a.ages.includes(input.ageRange)) return null;

  if (a.occasions?.includes(input.occasion)) breakdown.occasion = W.occasion;
  if (a.occasions && !a.occasions.includes(input.occasion)) return null;

  // --- budget ---------------------------------------------------------
  const fit = budgetFit(a, input.budgetMin, input.budgetMax);
  if (fit === 0) return null;
  breakdown.budget = W.budget * fit;

  // --- prazo ----------------------------------------------------------
  const urgent = input.deadlineDays !== null && input.deadlineDays <= 2;
  if (urgent) breakdown.prazo = a.digital ? W.urgentDigital : W.urgentPhysical;

  // --- pénalités ------------------------------------------------------
  if (input.avoidTitles.has(a.title)) breakdown.jaVisto = W.alreadyShown;
  if (input.rejected.has(a.title)) breakdown.recusado = W.rejected;

  breakdown.jitter = jitter(seed, a.id);

  const score = Object.values(breakdown).reduce((n, v) => n + v, 0);
  return { archetype: a, score, matched, breakdown };
}

/**
 * Choisit trois archétypes : les mieux notés, mais de trois catégories
 * DIFFÉRENTES, et en évitant de mettre les trois liens chez le même
 * marchand — répartir les clics répartit aussi le risque d'affiliation.
 */
export function pickThree(scored: Scored[]): Scored[] {
  const ranked = [...scored].sort((a, b) => b.score - a.score);
  const picked: Scored[] = [];
  const categories = new Set<string>();
  const stores = new Map<string, number>();

  const storePenalty = (s: Scored) => (stores.get(s.archetype.store) ?? 0) * 0.8;

  while (picked.length < 3) {
    const candidates = ranked.filter((s) => !categories.has(s.archetype.category) && !picked.includes(s));
    if (candidates.length === 0) break;

    const best = candidates.reduce((a, b) =>
      b.score - storePenalty(b) > a.score - storePenalty(a) ? b : a,
    );

    picked.push(best);
    categories.add(best.archetype.category);
    stores.set(best.archetype.store, (stores.get(best.archetype.store) ?? 0) + 1);
  }

  return picked;
}
