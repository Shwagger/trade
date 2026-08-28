import { BUDGETS, occasionLabel, relationLabel } from "./constants";

// "Para mãe · Aniversário · R$ 50 a R$ 150" — le rappel de ce que
// l'utilisateur a répondu, pour qu'il sache sur quoi porte la réponse.
export function headlineFor(input: {
  relation: string;
  occasion: string;
  budget: string;
}): string {
  return [relationLabel(input.relation), occasionLabel(input.occasion), input.budget].join(" · ");
}

export function budgetLabelFor(min: number, max: number | null): string {
  const match = BUDGETS.find((b) => b.min === min && b.max === max);
  if (match) return match.label;
  return max === null ? `R$ ${min} ou mais` : `R$ ${min} a R$ ${max}`;
}
