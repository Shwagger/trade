import { createHash } from "node:crypto";
import type { RequestPayload } from "./types";

// =====================================================================
// L'état de la demande tient dans l'URL.
//
// Le moteur étant déterministe (même entrée + même graine = même trio),
// on n'a besoin d'aucune base de données pour qu'une page de résultats
// s'affiche : le lien CONTIENT la demande. Conséquences :
//
//   - le site se déploie sans configurer quoi que ce soit ;
//   - un lien partagé dans un groupe WhatsApp affiche les mêmes trois
//     cartes pour tout le monde, aujourd'hui et dans six mois, même si
//     la base est vide ou tombe ;
//   - aucune ligne écrite pour un visiteur qui ne clique jamais.
//
// Supabase devient optionnel : il ne sert plus qu'à MESURER (sessions,
// clics, votes), jamais à faire marcher le produit.
//
// Ce n'est pas un secret et ça n'a pas à l'être : le contenu est ce que
// l'utilisateur vient de taper lui-même. On encode pour avoir une URL
// courte et propre, pas pour cacher.
// =====================================================================

/** Format compact : un tableau positionnel, pas des clés répétées. */
type Compact = [
  relation: string,
  ageRange: string,
  interests: string[],
  freeText: string,
  occasion: string,
  budgetId: string,
  deadlineId: string,
];

const b64urlEncode = (s: string) =>
  Buffer.from(s, "utf8").toString("base64").replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

const b64urlDecode = (s: string) =>
  Buffer.from(s.replace(/-/g, "+").replace(/_/g, "/"), "base64").toString("utf8");

export function encodeToken(p: RequestPayload): string {
  const compact: Compact = [
    p.relation,
    p.ageRange ?? "",
    (p.interests ?? []).slice(0, 12),
    (p.freeText ?? "").slice(0, 280),
    p.occasion,
    p.budgetId,
    p.deadlineId ?? "sem-pressa",
  ];
  return b64urlEncode(JSON.stringify(compact));
}

export function decodeToken(token: string): RequestPayload | null {
  try {
    const parsed = JSON.parse(b64urlDecode(token)) as unknown;
    if (!Array.isArray(parsed) || parsed.length < 6) return null;

    const [relation, ageRange, interests, freeText, occasion, budgetId, deadlineId] = parsed as Compact;
    if (typeof relation !== "string" || typeof occasion !== "string" || typeof budgetId !== "string") {
      return null;
    }

    return {
      relation,
      ageRange: typeof ageRange === "string" ? ageRange : "",
      interests: Array.isArray(interests) ? interests.filter((i) => typeof i === "string").slice(0, 12) : [],
      freeText: typeof freeText === "string" ? freeText.slice(0, 280) : "",
      occasion,
      budgetId,
      deadlineId: typeof deadlineId === "string" ? deadlineId : "sem-pressa",
    };
  } catch {
    // Lien tronqué par un client de messagerie, ou trafiqué : on rend
    // null et l'appelant affiche une 404 propre.
    return null;
  }
}

/**
 * Identifiant stable dérivé du jeton, au format UUID.
 *
 * Sert de clé en base quand Supabase est branché : deux personnes qui
 * ouvrent le même lien partagé partagent la même ligne, donc leurs votes
 * s'additionnent. Sans Supabase, c'est simplement une clé locale.
 */
export function requestKey(token: string): string {
  const h = createHash("sha256").update(token).digest("hex");
  return [h.slice(0, 8), h.slice(8, 12), "5" + h.slice(13, 16), "8" + h.slice(17, 20), h.slice(20, 32)].join("-");
}
