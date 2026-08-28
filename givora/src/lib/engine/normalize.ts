// ---------------------------------------------------------------------
// Normalisation du texte libre. Les gens tapent « cafe », « CAFÉ »,
// « ela ama café ☕ » — c'est le même signal. Sans cette étape, la moitié
// des correspondances sont perdues sur un accent.
// ---------------------------------------------------------------------

/** minuscules, sans accents, ponctuation ramenée à des espaces. */
export function normalize(text: string): string {
  return text
    .toLowerCase()
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")   // enlève les diacritiques
    .replace(/[^a-z0-9\s]/g, " ")      // emoji, ponctuation, tout dehors
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Vrai si `needle` apparaît comme mot (ou début de mot) dans `haystack`.
 *
 * Le préfixe compte : « corre », « correndo » et « corrida » doivent tous
 * matcher le motif « corr ». Mais on exige une frontière de mot à gauche,
 * sinon « pai » matcherait « chinelo de capai... » et on sort n'importe quoi.
 */
export function containsWord(haystack: string, needle: string): boolean {
  const i = haystack.indexOf(needle);
  if (i === -1) return false;
  const before = i === 0 ? " " : haystack[i - 1];
  return before === " ";
}
