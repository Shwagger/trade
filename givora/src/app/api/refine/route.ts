import { NextResponse } from "next/server";
import { clientIp, hit } from "@/lib/rate-limit";
import { decodeToken, encodeToken } from "@/lib/token";

// POST /api/refine  { token, feedback }
//
// Le « refinar » ne relit rien : il fabrique un NOUVEAU jeton en
// ajoutant le retour de l'utilisateur à sa description. Le résultat
// affiné est donc lui aussi une URL partageable, et il reste identique
// pour tous ceux qui l'ouvriront.
export async function POST(req: Request) {
  const rate = hit(clientIp(req));
  if (!rate.allowed) {
    return NextResponse.json(
      { error: "Você pediu muitas ideias seguidas. Respire e tente daqui a pouco." },
      { status: 429, headers: { "Retry-After": String(rate.retryAfterSeconds) } },
    );
  }

  let body: { token?: string; feedback?: string };
  try {
    body = (await req.json()) as { token?: string; feedback?: string };
  } catch {
    return NextResponse.json({ error: "JSON inválido." }, { status: 400 });
  }

  const payload = decodeToken((body.token ?? "").trim());
  if (!payload) return NextResponse.json({ error: "Link inválido." }, { status: 400 });

  const feedback = (body.feedback ?? "").slice(0, 280).trim();
  if (feedback.length < 3) {
    return NextResponse.json({ error: "Conte um pouco mais do que não encaixou." }, { status: 400 });
  }

  // Le retour entre dans le même extracteur de signaux que la description
  // d'origine : « prefiro algo para a casa » ajoute vraiment le signal
  // « casa », il n'est pas juste concaténé pour faire joli.
  return NextResponse.json({
    token: encodeToken({
      ...payload,
      freeText: [payload.freeText, feedback].filter(Boolean).join(" — "),
    }),
  });
}
