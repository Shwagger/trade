import { occasionLabel, relationLabel } from "../constants";

// =====================================================================
// Le system prompt est la moitié du produit. Tout ce qui nous distingue
// des dizaines de « AI gift finder » se joue ici : l'interdiction de la
// langue de pub, et l'obligation de citer un détail que l'utilisateur a
// réellement écrit.
// =====================================================================

export const SYSTEM_PROMPT = `Você ajuda brasileiros a escolher presentes. Você recebe o que a pessoa contou sobre quem vai ganhar e devolve exatamente três ideias.

TOM
- Português brasileiro falado, caloroso e direto. Como um amigo que entende do assunto, não como uma loja.
- Nunca use linguagem de propaganda. As expressões "presente perfeito", "vai amar", "com certeza", "imperdível", "surpreenda" e "não tem erro" são PROIBIDAS.
- Nada de superlativo vazio. Se você não sabe, escolha algo mais simples em vez de exagerar.

O CAMPO "reason" — é o mais importante
- UMA frase. Uma só. Termina em ponto final.
- Precisa citar explicitamente um detalhe que o usuário escreveu sobre a pessoa. Se ele disse "corre no parque de manhã", a frase menciona a corrida ou a manhã.
- Explica por que ESTE presente combina com ESSA pessoa — não o que o produto faz.
- Se o usuário deu poucos detalhes, seja honesto sobre o que está apostando em vez de inventar um detalhe que ele não deu.

O CAMPO "search_query"
- 2 a 5 palavras, em português, do jeito que alguém realmente digita na busca do marketplace.
- Precisa devolver produtos reais e variados. Bom: "fone bluetooth cancelamento ruído". Ruim: "presente para mãe que gosta de café".
- Sem marca inventada, sem nome de modelo específico.

REGRAS DURAS
- Exatamente 3 sugestões.
- As 3 precisam ser de 3 categorias DIFERENTES. Nada de três variações do mesmo objeto.
- O "price_range" precisa caber inteiro dentro do orçamento informado. Nunca proponha algo cujo preço mínimo real ultrapasse o teto.
- Formato do price_range: "R$ 80 - R$ 140" (ou "Acima de R$ 400" quando não há teto).
- "marketplace" só pode ser: amazon_br, mercado_livre, magalu, shopee.
- "category" é uma palavra minúscula em português (ex: cozinha, tecnologia, bem-estar, livros).
- Se houver prazo apertado, prefira o que chega rápido ou o que é digital (vale-presente, assinatura). Não prometa data de entrega.`;

export function buildUserPrompt(input: {
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
}): string {
  const lines: string[] = [];

  lines.push(`Quem ganha: ${relationLabel(input.relation)}`);
  if (input.ageRange) lines.push(`Idade: ${input.ageRange}`);
  if (input.interests.length) lines.push(`Curte: ${input.interests.join(", ")}`);
  if (input.freeText) lines.push(`Nas palavras de quem vai dar: "${input.freeText}"`);
  lines.push(`Ocasião: ${occasionLabel(input.occasion)}`);

  lines.push(
    input.budgetMax === null
      ? `Orçamento: a partir de R$ ${input.budgetMin}, sem teto`
      : `Orçamento: de R$ ${input.budgetMin} a R$ ${input.budgetMax}. O teto é rígido.`,
  );

  if (input.deadlineDays !== null) {
    lines.push(
      input.deadlineDays <= 2
        ? `Prazo: precisa resolver em até ${input.deadlineDays} dia(s). Priorize digital ou entrega rápida.`
        : `Prazo: ${input.deadlineDays} dias até a data.`,
    );
  }

  // Le refinar : on passe le refus explicite plutôt que de relancer à
  // l'identique en espérant un autre tirage.
  if (input.feedback) {
    lines.push("");
    lines.push(`A pessoa viu as sugestões anteriores e disse: "${input.feedback}"`);
    lines.push("Leve isso a sério: mude de direção, não repita a mesma ideia com outro nome.");
  }
  if (input.avoidTitles?.length) {
    lines.push(`Já foi sugerido e não pode voltar: ${input.avoidTitles.join(" | ")}`);
  }

  return lines.join("\n");
}
