// Toutes les options du formulaire vivent ici : un seul fichier à toucher
// pour ajouter une relation, une occasion ou une tranche de budget.

export const RELATIONS = [
  { id: "mae", label: "Mãe", emoji: "👩" },
  { id: "pai", label: "Pai", emoji: "👨" },
  { id: "namorada", label: "Namorada", emoji: "💗" },
  { id: "namorado", label: "Namorado", emoji: "💙" },
  { id: "esposa", label: "Esposa", emoji: "💍" },
  { id: "marido", label: "Marido", emoji: "💍" },
  { id: "amigo", label: "Amigo(a)", emoji: "🤝" },
  { id: "colega", label: "Colega", emoji: "💼" },
  { id: "filho", label: "Filho(a)", emoji: "🧒" },
  { id: "irmao", label: "Irmão / Irmã", emoji: "👯" },
  { id: "avo", label: "Avó / Avô", emoji: "🧓" },
  { id: "outro", label: "Outra pessoa", emoji: "🎁" },
] as const;

export const AGE_RANGES = [
  { id: "0-12", label: "Criança" },
  { id: "13-17", label: "13-17" },
  { id: "18-24", label: "18-24" },
  { id: "25-34", label: "25-34" },
  { id: "35-49", label: "35-49" },
  { id: "50-64", label: "50-64" },
  { id: "65+", label: "65+" },
] as const;

// Chips de départ. Ce n'est pas une liste fermée : le champ libre reste roi,
// les chips servent juste à débloquer l'utilisateur qui ne sait pas quoi taper.
export const INTEREST_CHIPS = [
  "cozinha",
  "café",
  "academia",
  "corrida",
  "praia",
  "jardinagem",
  "leitura",
  "música",
  "games",
  "séries",
  "viagem",
  "moda",
  "skincare",
  "pets",
  "futebol",
  "artesanato",
  "fotografia",
  "vinho",
  "tecnologia",
  "decoração",
] as const;

export const OCCASIONS = [
  { id: "aniversario", label: "Aniversário", emoji: "🎂" },
  { id: "natal", label: "Natal", emoji: "🎄" },
  { id: "dia-das-maes", label: "Dia das Mães", emoji: "💐" },
  { id: "dia-dos-pais", label: "Dia dos Pais", emoji: "🍻" },
  { id: "amigo-secreto", label: "Amigo secreto", emoji: "🤫" },
  { id: "namorados", label: "Dia dos Namorados", emoji: "❤️" },
  { id: "sem-motivo", label: "Sem motivo", emoji: "✨" },
] as const;

// budget_max null = pas de plafond ("R$300+").
export const BUDGETS = [
  { id: "ate-50", label: "Até R$ 50", hint: "lembrancinha", min: 0, max: 50 },
  { id: "50-150", label: "R$ 50 a R$ 150", hint: "o mais escolhido", min: 50, max: 150 },
  { id: "150-300", label: "R$ 150 a R$ 300", hint: "presente caprichado", min: 150, max: 300 },
  { id: "300-mais", label: "R$ 300 ou mais", hint: "sem limite", min: 300, max: null },
] as const;

// « Precisa chegar até quando ? » — la vraie angoisse du cadeau n'est pas
// le goût, c'est le retard. Le moteur s'en sert pour privilégier le
// numérique quand le délai est court.
export const DEADLINES = [
  { id: "sem-pressa", label: "Sem pressa", days: null },
  { id: "semana", label: "Esta semana", days: 7 },
  { id: "3-dias", label: "Em 3 dias", days: 3 },
  { id: "amanha", label: "É pra amanhã", days: 1 },
] as const;

export function deadlineById(id: string) {
  return DEADLINES.find((d) => d.id === id) ?? DEADLINES[0];
}

export function deadlineLabelFor(days: number | null): string | null {
  if (days === null) return null;
  return DEADLINES.find((d) => d.days === days)?.label ?? `Em ${days} dias`;
}

export const MARKETPLACE_LABELS: Record<string, string> = {
  amazon_br: "Amazon",
  mercado_livre: "Mercado Livre",
  magalu: "Magalu",
  shopee: "Shopee",
};

// Le CTA est écrit en entier : l'article change selon la boutique
// ("na Amazon" mais "no Mercado Livre"), ça ne se compose pas.
export const MARKETPLACE_CTA: Record<string, string> = {
  amazon_br: "Ver na Amazon",
  mercado_livre: "Ver no Mercado Livre",
  magalu: "Ver no Magalu",
  shopee: "Ver na Shopee",
};

export function relationLabel(id: string): string {
  return RELATIONS.find((r) => r.id === id)?.label ?? "essa pessoa";
}

export function occasionLabel(id: string): string {
  return OCCASIONS.find((o) => o.id === id)?.label ?? "a ocasião";
}

export function budgetById(id: string) {
  return BUDGETS.find((b) => b.id === id) ?? BUDGETS[1];
}
