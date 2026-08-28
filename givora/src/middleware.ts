import { NextResponse, type NextRequest } from "next/server";

// ---------------------------------------------------------------------
// Pose un cookie `session_id` anonyme. C'était prévu pour la phase 3
// (tracking), mais le vote WhatsApp en a besoin dès maintenant : sans
// identité de visiteur, impossible de dire « un avis par personne ».
//
// Aucune donnée personnelle : un UUID aléatoire, rien d'autre.
// ---------------------------------------------------------------------

const COOKIE = "givora_sid";
const MAX_AGE = 60 * 60 * 24 * 180; // 180 jours

export function middleware(req: NextRequest) {
  const res = NextResponse.next();

  if (!req.cookies.get(COOKIE)) {
    res.cookies.set(COOKIE, crypto.randomUUID(), {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      maxAge: MAX_AGE,
      path: "/",
    });
  }

  // Source de la visite. Posée une seule fois : on veut la PREMIÈRE
  // origine, pas la dernière — sinon un partage WhatsApp réécrit
  // l'attribution de la campagne qui a amené la personne.
  const utm = ["utm_source", "utm_medium", "utm_campaign"]
    .map((k) => [k, req.nextUrl.searchParams.get(k)] as const)
    .filter((entry): entry is readonly [string, string] => entry[1] !== null);

  if (utm.length > 0 && !req.cookies.get("givora_src")) {
    res.cookies.set("givora_src", JSON.stringify(Object.fromEntries(utm)), {
      httpOnly: true,
      sameSite: "lax",
      secure: process.env.NODE_ENV === "production",
      maxAge: MAX_AGE,
      path: "/",
    });
  }

  return res;
}

export const config = {
  // Ni les assets, ni les images : le cookie n'a rien à y faire.
  matcher: ["/((?!_next/static|_next/image|favicon.ico|icon-|manifest).*)"],
};
