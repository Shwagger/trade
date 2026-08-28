import { NextResponse } from "next/server";
import { buildAffiliateUrl } from "@/lib/affiliates";
import { suggestionsFromToken } from "@/lib/build-suggestions";
import { decodeToken } from "@/lib/token";
import { recordClick } from "@/lib/store";
import { sessionIdFrom } from "@/lib/session";

// GET /go/[token]/[position]
//
// Toute sortie vers un marchand passe par ici :
//   1. c'est le seul endroit où le clic est mesuré, et le taux de clic
//      sortant est LA métrique du produit ;
//   2. l'URL affiliée n'apparaît jamais dans le HTML — le tag n'est pas
//      lisible dans le code source, et changer de programme
//      d'affiliation ne demande pas de re-rendre une carte.
//
// La destination est recalculée depuis le jeton, donc la redirection
// fonctionne même sans base de données.
export const dynamic = "force-dynamic";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ token: string; position: string }> },
) {
  const { token, position } = await params;
  const payload = decodeToken(token);
  const index = Number(position) - 1;

  if (!payload || !Number.isInteger(index) || index < 0 || index > 2) {
    return NextResponse.redirect(new URL("/", req.url), 302);
  }

  const suggestion = suggestionsFromToken(token, payload)[index];
  if (!suggestion) return NextResponse.redirect(new URL("/", req.url), 302);

  // Mesure en meilleur effort : un échec d'enregistrement ne doit jamais
  // empêcher la redirection. On perd une donnée, pas une commission.
  await recordClick({
    suggestionId: suggestion.id,
    referrer: req.headers.get("referer"),
    userAgent: req.headers.get("user-agent"),
    sessionId: sessionIdFrom(req) || null,
  }).catch((err) => console.error("[go] clic non enregistré:", err));

  const destination = buildAffiliateUrl(
    suggestion.marketplace,
    suggestion.search_query,
    suggestion.price_range,
  );

  // 302 et non 301 : la destination dépend de la config d'affiliation,
  // qui change. Un 301 mis en cache figerait un tag périmé.
  return NextResponse.redirect(destination, {
    status: 302,
    headers: { "Cache-Control": "no-store" },
  });
}
