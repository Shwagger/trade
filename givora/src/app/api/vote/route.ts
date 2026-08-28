import { NextResponse } from "next/server";
import { suggestionsFromToken } from "@/lib/build-suggestions";
import { decodeToken, requestKey } from "@/lib/token";
import { castVote, getTallies } from "@/lib/store";
import { sessionIdFrom } from "@/lib/session";

// POST /api/vote  { token, position: 1 | 2 | 3, value: 1 | -1 }
//
// Le cœur du partage WhatsApp : le groupe vote sur les trois cartes.
//
// La validation se fait contre le JETON, pas contre la base : depuis que
// l'état vit dans l'URL, plus rien n'écrit les suggestions avant un vote.
// On reconstruit donc les trois cartes depuis le lien et on vérifie que
// la position existe — ce qui marche aussi quand Supabase est absent.
export async function POST(req: Request) {
  const sessionId = sessionIdFrom(req);
  if (!sessionId) {
    return NextResponse.json({ error: "Sessão não encontrada. Recarregue a página." }, { status: 400 });
  }

  let body: { token?: string; position?: number; value?: number };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "JSON inválido." }, { status: 400 });
  }

  const token = (body.token ?? "").trim();
  const payload = decodeToken(token);
  const position = Number(body.position);
  const value = body.value === 1 ? 1 : body.value === -1 ? -1 : null;

  if (!payload || ![1, 2, 3].includes(position) || value === null) {
    return NextResponse.json({ error: "Voto inválido." }, { status: 400 });
  }

  const requestId = requestKey(token);
  const suggestion = suggestionsFromToken(token, payload).find((s) => s.position === position);
  if (!suggestion) {
    return NextResponse.json({ error: "Sugestão não encontrada." }, { status: 404 });
  }

  try {
    await castVote({ suggestionId: suggestion.id, requestId, sessionId, value });
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
