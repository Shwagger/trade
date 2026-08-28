import type { Archetype } from "./catalog";
import type { Signal } from "./lexicon";

// =====================================================================
// La phrase « por que combina ». UNE phrase, et elle doit citer un
// détail que la personne a réellement donné — c'est la règle qui nous
// sépare des concurrents, et elle est appliquée par construction ici :
// on ne peut pas citer un signal qu'on n'a pas extrait de son texte.
//
// Les gabarits sont choisis pour que `display` (« o café », « as plantas »,
// « os cuidados com a pele ») s'y insère sans casser la grammaire. Pas de
// contraction de préposition, pas d'accord à deviner.
// =====================================================================

const MATCHED = [
  (d: string, n: string) => `Você mencionou ${d}: ${n}.`,
  (d: string, n: string) => `Combina com ${d} que você descreveu, e ${n}.`,
  (d: string, n: string) => `Pelo que você contou sobre ${d}, ${n}.`,
];

// Quand rien n'a matché, on le dit. Un concurrent inventerait un détail ;
// nous on assume l'incertitude — ça se lit comme de l'honnêteté, pas
// comme un échec.
const NEUTRAL = [
  (n: string) => `Sem muita pista, essa é a aposta de baixo risco: ${n}.`,
  (n: string) => `Funciona mesmo sem saber muito da pessoa, porque ${n}.`,
  (n: string) => `Escolha segura pelo que você contou: ${n}.`,
];

// Prazo court : la livraison devient l'argument principal.
const URGENT = (n: string) => `Chega na hora porque é digital, e ${n}.`;

export function buildReason(input: {
  archetype: Archetype;
  matched: Signal | null;
  position: number;
  urgent: boolean;
}): string {
  const { archetype, matched, position, urgent } = input;

  if (urgent && archetype.digital) return URGENT(archetype.note);

  // La position fait tourner le gabarit : trois cartes qui commencent
  // toutes par « Você mencionou » se lisent comme un formulaire.
  if (matched) return MATCHED[position % MATCHED.length](matched.display, archetype.note);
  return NEUTRAL[position % NEUTRAL.length](archetype.note);
}
