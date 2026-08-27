import { NextResponse } from "next/server";
import { castVote, getSuggestions, getTallies } from "@/lib/store";
import { sessionIdFrom } from "@/lib/session";

// POST /api/vote  { requestId, suggestionId, value: 1 | -1 }
//
// Le cœur du partage WhatsApp : le groupe vote sur les trois cartes.
// Renvoie le décompte à jour pour que l'écran se mette à jour sans
// recharger.
export async function POST(req: Request) {
  const sessionId = sessionIdFrom(req);
  if (!sessionId) {
    return NextResponse.json({ error: "Sessão não encontrada. Recarregue a página." }, { status: 400 });
  }

  let body: { requestId?: string; suggestionId?: string; value?: number };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "JSON inválido." }, { status: 400 });
  }

  const requestId = (body.requestId ?? "").trim();
  const suggestionId = (body.suggestionId ?? "").trim();
  const value = body.value === 1 ? 1 : body.value === -1 ? -1 : null;

  if (!requestId || !suggestionId || value === null) {
    return NextResponse.json({ error: "Voto inválido." }, { status: 400 });
  }

  try {
    // La suggestion doit bien appartenir à cette demande : sans ça
    // n'importe qui peut voter sur la carte de quelqu'un d'autre.
    const suggestions = await getSuggestions(requestId);
    if (!suggestions.some((s) => s.id === suggestionId)) {
      return NextResponse.json({ error: "Sugestão não encontrada." }, { status: 404 });
    }

    await castVote({ suggestionId, requestId, sessionId, value });
    return NextResponse.json({ tallies: await getTallies(requestId, sessionId) });
  } catch (err) {
    console.error("[api/vote]", err);
    return NextResponse.json({ error: "Não deu para registrar o voto." }, { status: 500 });
  }
}

// GET /api/vote?requestId=... — les votes du groupe, pour rafraîchir.
export async function GET(req: Request) {
  const requestId = new URL(req.url).searchParams.get("requestId") ?? "";
  if (!requestId) return NextResponse.json({ error: "requestId ausente." }, { status: 400 });

  try {
    return NextResponse.json({ tallies: await getTallies(requestId, sessionIdFrom(req)) });
  } catch (err) {
    console.error("[api/vote GET]", err);
    return NextResponse.json({ error: "Não deu para ler os votos." }, { status: 500 });
  }
}
