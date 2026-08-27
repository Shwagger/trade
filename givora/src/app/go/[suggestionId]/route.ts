import { NextResponse } from "next/server";
import { buildAffiliateUrl } from "@/lib/affiliates";
import { getSuggestionById, recordClick } from "@/lib/store";
import { sessionIdFrom } from "@/lib/session";

// GET /go/[suggestionId]
//
// Toute sortie vers un marchand passe par ici. Deux raisons :
//   1. c'est le seul endroit où le clic est mesuré, et le taux de clic
//      sortant est LA métrique du produit ;
//   2. l'URL affiliée n'apparaît jamais dans le HTML — le tag n'est pas
//      lisible dans le code source de la page, et on peut changer de
//      programme d'affiliation sans re-rendre une seule carte.
//
// Le clic est enregistré avant la redirection, mais un échec
// d'enregistrement ne bloque jamais : on perd une mesure, pas une vente.
export const dynamic = "force-dynamic";

export async function GET(
  req: Request,
  { params }: { params: Promise<{ suggestionId: string }> },
) {
  const { suggestionId } = await params;

  let suggestion;
  try {
    suggestion = await getSuggestionById(suggestionId);
  } catch (err) {
    console.error("[go] lecture:", err);
    suggestion = null;
  }

  // Id inconnu : on renvoie à l'accueil plutôt qu'une page d'erreur.
  if (!suggestion) {
    return NextResponse.redirect(new URL("/", req.url), 302);
  }

  await recordClick({
    suggestionId,
    referrer: req.headers.get("referer"),
    userAgent: req.headers.get("user-agent"),
    sessionId: sessionIdFrom(req) || null,
  });

  const destination = buildAffiliateUrl(
    suggestion.marketplace,
    suggestion.search_query,
    suggestion.price_range,
  );

  // 302 et non 301 : la destination dépend de la config d'affiliation,
  // qui change. Un 301 serait mis en cache par le navigateur et figerait
  // un tag périmé.
  return NextResponse.redirect(destination, {
    status: 302,
    headers: { "Cache-Control": "no-store" },
  });
}
