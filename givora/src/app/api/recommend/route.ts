import { NextResponse } from "next/server";
import { getRecipient, getRequest, getSuggestions, replaceSuggestions } from "@/lib/store";
import { stubSuggestions } from "@/lib/recommend/stub";

// POST /api/recommend  { requestId, feedback? }
//
// PHASE 1 : les suggestions viennent d'un catalogue en dur (lib/recommend/stub).
// PHASE 2 : ce handler appellera l'API Anthropic (claude-sonnet-4-6), validera
// la sortie avec Zod, retentera une fois si le JSON est invalide, et posera un
// rate limit par IP. La signature de la route et la forme de la réponse ne
// changent pas — l'écran de résultats n'aura rien à modifier.
export async function POST(req: Request) {
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

  try {
    const request = await getRequest(requestId);
    if (!request) {
      return NextResponse.json({ error: "Pedido não encontrado." }, { status: 404 });
    }

    const recipient = request.recipient_id ? await getRecipient(request.recipient_id) : null;
    const feedback = (body.feedback ?? "").slice(0, 500).trim();

    // "Refinar" : on refuse de resservir exactement le même trio.
    const previous = feedback ? await getSuggestions(requestId) : [];

    const drafts = stubSuggestions({
      occasion: request.occasion,
      interests: recipient?.interests ?? [],
      // Le "refinar" est simplement concaténé à l'entrée libre. En phase 2
      // il partira dans un tour de conversation dédié.
      freeText: [request.raw_input, feedback].filter(Boolean).join(" — "),
      budgetMin: request.budget_min,
      budgetMax: request.budget_max,
      avoidTitles: previous.map((s) => s.title),
    });

    const suggestions = await replaceSuggestions(requestId, drafts);
    return NextResponse.json({ suggestions });
  } catch (err) {
    console.error("[api/recommend]", err);
    return NextResponse.json(
      { error: "Não conseguimos gerar as ideias agora. Tente de novo." },
      { status: 500 },
    );
  }
}
