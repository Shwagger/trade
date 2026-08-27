import Anthropic from "@anthropic-ai/sdk";
import { zodOutputFormat } from "@anthropic-ai/sdk/helpers/zod";
import type { SuggestionDraft } from "../store";
import { buildUserPrompt, SYSTEM_PROMPT } from "./prompt";
import { checkRules, RecommendationSchema, withinBudget, type ModelSuggestion } from "./schema";

// =====================================================================
// Moteur de recommandation — appel Anthropic.
//
// Sortie structurée : `messages.parse` + `zodOutputFormat` contraignent
// le modèle au schéma côté serveur d'Anthropic, donc on ne parse pas du
// JSON à la main dans du texte. On revalide quand même à l'arrivée : le
// schéma garantit la forme, pas les règles produit (3 catégories
// différentes, budget, pas de langue de pub).
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
};

export class EngineError extends Error {
  constructor(
    message: string,
    /** Message montré à l'utilisateur, en PT-BR. */
    readonly userMessage: string,
  ) {
    super(message);
    this.name = "EngineError";
  }
}

export function isEngineConfigured(): boolean {
  return Boolean(process.env.ANTHROPIC_API_KEY);
}

// Le modèle est fixé ici et nulle part ailleurs.
const MODEL = "claude-sonnet-4-6";

// Un utilisateur qui attend plus de 20 s est déjà parti. Mieux vaut une
// erreur propre et un bouton « tentar de novo » qu'un spinner infini.
const TIMEOUT_MS = 20_000;

let client: Anthropic | null = null;
function getClient(): Anthropic {
  if (!client) {
    client = new Anthropic({
      timeout: TIMEOUT_MS,
      maxRetries: 1, // le SDK gère déjà 429 / 5xx / erreurs réseau
    });
  }
  return client;
}

async function callOnce(input: EngineInput, extraInstruction?: string): Promise<ModelSuggestion[]> {
  const userPrompt = extraInstruction
    ? `${buildUserPrompt(input)}\n\n${extraInstruction}`
    : buildUserPrompt(input);

  const response = await getClient().messages.parse({
    model: MODEL,
    max_tokens: 2000,
    // Effort bas : la tâche est courte et la latence est le produit.
    output_config: {
      effort: "low",
      format: zodOutputFormat(RecommendationSchema),
    },
    system: SYSTEM_PROMPT,
    messages: [{ role: "user", content: userPrompt }],
  });

  const parsed = response.parsed_output;
  if (!parsed) throw new Error("resposta sem parsed_output");
  return parsed.suggestions;
}

/**
 * Génère les 3 suggestions. Une seule relance en cas de sortie invalide
 * ou non conforme aux règles produit — au-delà, on rend la main.
 */
export async function generateWithAnthropic(input: EngineInput): Promise<SuggestionDraft[]> {
  let suggestions: ModelSuggestion[] | null = null;
  let problems: string[] = [];

  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      // À la seconde tentative on dit au modèle ce qui n'allait pas :
      // relancer à l'identique ne corrige rien.
      const correction =
        attempt === 0
          ? undefined
          : `A tentativa anterior foi rejeitada por: ${problems.join(" ; ")}. Corrija exatamente esses pontos.`;

      const candidate = await callOnce(input, correction);

      problems = checkRules(candidate);
      for (const s of candidate) {
        if (!withinBudget(s.price_range, input.budgetMin, input.budgetMax)) {
          problems.push(`fora do orçamento: "${s.price_range}"`);
        }
      }

      if (problems.length === 0) {
        suggestions = candidate;
        break;
      }

      // Dernière tentative : on sert quand même. Trois idées imparfaites
      // valent mieux qu'une page d'erreur.
      if (attempt === 1) {
        console.warn("[engine] servi malgré des règles non respectées:", problems);
        suggestions = candidate;
      }
    } catch (err) {
      if (attempt === 1) throw toEngineError(err);
      console.warn("[engine] tentative 1 échouée, on relance:", err);
    }
  }

  if (!suggestions) {
    throw new EngineError("aucune suggestion", "Não conseguimos gerar as ideias agora.");
  }

  return suggestions.map((s, i) => ({
    title: s.title.trim(),
    reason: s.reason.trim(),
    category: s.category.trim().toLowerCase(),
    search_query: s.search_query.trim(),
    price_range: s.price_range.trim(),
    marketplace: s.marketplace,
    position: i + 1,
  }));
}

function toEngineError(err: unknown): EngineError {
  if (err instanceof Anthropic.APIConnectionTimeoutError) {
    return new EngineError("timeout", "Demorou demais para responder. Toque para tentar de novo.");
  }
  if (err instanceof Anthropic.RateLimitError) {
    return new EngineError("rate limit", "Muita gente pedindo ideia agora. Tente daqui a pouco.");
  }
  if (err instanceof Anthropic.AuthenticationError) {
    return new EngineError("auth", "Configuração do servidor incorreta. Já estamos vendo isso.");
  }
  if (err instanceof Anthropic.APIError) {
    return new EngineError(`api ${err.status}`, "O motor de sugestões falhou. Tente de novo.");
  }
  return new EngineError(String(err), "Algo deu errado aqui do nosso lado. Tente de novo.");
}
