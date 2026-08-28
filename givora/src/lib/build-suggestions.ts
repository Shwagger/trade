import { budgetById, deadlineById } from "./constants";
import { recommend } from "./engine";
import { requestKey } from "./token";
import type { RequestPayload, Suggestion } from "./types";

// ---------------------------------------------------------------------
// Un seul endroit calcule les trois cartes à partir d'un jeton. La page
// de résultats, la route /go et le partage passent tous par ici, donc
// ils ne peuvent pas diverger : le lien qu'on partage mène exactement
// aux cartes qu'on a vues.
// ---------------------------------------------------------------------

export function suggestionsFromToken(token: string, payload: RequestPayload, feedback?: string): Suggestion[] {
  const budget = budgetById(payload.budgetId);
  const deadline = deadlineById(payload.deadlineId);
  const requestId = requestKey(token);

  const drafts = recommend({
    relation: payload.relation,
    ageRange: payload.ageRange || null,
    interests: payload.interests,
    freeText: payload.freeText || null,
    occasion: payload.occasion,
    budgetMin: budget.min,
    budgetMax: budget.max,
    deadlineDays: deadline.days,
    feedback: feedback || null,
    // La graine est le jeton : deux personnes qui ouvrent le même lien
    // voient exactement les mêmes cartes.
    seed: token,
  });

  return drafts.map((d) => ({
    ...d,
    // Id déterministe : /go/[token]/[position] doit pouvoir reconstruire
    // la même suggestion sans rien lire en base.
    id: `${requestId}:${d.position}`,
    request_id: requestId,
  }));
}
