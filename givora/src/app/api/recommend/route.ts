import { NextResponse } from "next/server";
import {
  getRecipient,
  getRequest,
  getSuggestions,
  rejectedTitles,
  replaceSuggestions,
} from "@/lib/store";
import { clientIp, hit } from "@/lib/rate-limit";
import { recommend } from "@/lib/engine";
import {
  EngineError,
  generateWithAnthropic,
  isAiEngineEnabled,
} from "@/lib/recommend/anthropic";

// POST /api/recommend  { requestId, feedback? }
//
// Le moteur : Anthropic quand la clé est là, catalogue de secours sinon
// (dev local sans credentials, et filet si l'API tombe — mieux vaut trois
// idées correctes qu'une page d'erreur).
export async function POST(req: Request) {
  const rate = hit(clientIp(req));
  if (!rate.allowed) {
    return NextResponse.json(
      { error: "Você pediu muitas ideias seguidas. Respire e tente daqui a pouco." },
      { status: 429, headers: { "Retry-After": String(rate.retryAfterSeconds) } },
    );
  }

  let body: { requestId?: string; feedback?: string };
  try {
    body = (await req.json()) as { requestId?: string; feedback?: string };
  } catch {
    return NextResponse.json({ error: "JSON inválido." }, { status: 400 });
  }

  const requestId = (body.requestId ?? "").trim();
  if (!requestId) {
    return NextResponse.json({ error: "requestId ausente." }, { status: 400 });
  }

  let request, recipient, feedback: string, avoidTitles: string[];
  try {
    request = await getRequest(requestId);
    if (!request) {
      return NextResponse.json({ error: "Pedido não encontrado." }, { status: 404 });
    }

    recipient = request.recipient_id ? await getRecipient(request.recipient_id) : null;
    feedback = (body.feedback ?? "").slice(0, 500).trim();

    // Le refinar n'oublie pas ce qui a déjà été proposé, ni ce que le
    // groupe a descendu dans le vote WhatsApp.
    avoidTitles = feedback
      ? [
          ...(await getSuggestions(requestId)).map((s) => s.title),
          ...(await rejectedTitles(requestId)),
        ]
      : await rejectedTitles(requestId);
  } catch (err) {
    console.error("[api/recommend] lecture:", err);
    return NextResponse.json({ error: "Não conseguimos ler seu pedido." }, { status: 500 });
  }

  const input = {
    relation: recipient?.relation ?? "outro",
    ageRange: recipient?.age_range ?? null,
    interests: recipient?.interests ?? [],
    freeText: request.raw_input,
    occasion: request.occasion,
    budgetMin: request.budget_min,
    budgetMax: request.budget_max,
    deadlineDays: request.deadline_days,
    feedback: feedback || null,
    avoidTitles: [...new Set(avoidTitles)],
  };

  let drafts;
  let engine: "algoritmo" | "ia" = "algoritmo";

  // Par défaut : l'algorithme. Zéro appel réseau, zéro coût par session,
  // réponse en quelques millisecondes. La commission est une marge de
  // 100 %, et la facture ne bouge pas quand le trafic monte.
  //
  // L'IA n'est là que si on l'active explicitement (USE_AI_ENGINE=1 +
  // clé). Elle coûte de l'argent à chaque demande : c'est un choix à
  // faire les yeux ouverts, pas un défaut.
  if (isAiEngineEnabled()) {
    try {
      drafts = await generateWithAnthropic(input);
      engine = "ia";
    } catch (err) {
      // L'IA tombe ou dépasse le délai : l'algorithme prend la main tout
      // de suite. L'utilisateur ne voit jamais d'erreur pour ça.
      console.error("[api/recommend] IA en échec, bascule sur l'algorithme:", err);
      if (!(err instanceof EngineError)) console.error(err);
      drafts = recommend({ ...input, seed: requestId });
    }
  } else {
    drafts = recommend({ ...input, seed: requestId });
  }

  try {
    const suggestions = await replaceSuggestions(requestId, drafts);
    return NextResponse.json({ suggestions, engine });
  } catch (err) {
    console.error("[api/recommend] écriture:", err);
    return NextResponse.json({ error: "Não conseguimos salvar as ideias." }, { status: 500 });
  }
}
