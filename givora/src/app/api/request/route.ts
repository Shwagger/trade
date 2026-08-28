import { NextResponse } from "next/server";
import { budgetById, deadlineById } from "@/lib/constants";
import { encodeToken, requestKey } from "@/lib/token";
import { createRecipient, createRequest } from "@/lib/store";
import { isSupabaseConfigured } from "@/lib/supabase";
import type { RequestPayload } from "@/lib/types";

// POST /api/request
//
// Renvoie le JETON qui sert d'URL de résultat. Le jeton CONTIENT la
// demande, donc la page de résultats n'a besoin d'aucune base : le site
// se déploie sans configurer quoi que ce soit.
//
// Quand Supabase est branché, on enregistre aussi la demande — mais
// seulement pour la MESURE (/admin), jamais pour faire marcher le
// produit. Un échec d'écriture ne doit donc rien casser.
export async function POST(req: Request) {
  let body: RequestPayload;
  try {
    body = (await req.json()) as RequestPayload;
  } catch {
    return NextResponse.json({ error: "JSON inválido." }, { status: 400 });
  }

  const relation = (body.relation ?? "").trim();
  const occasion = (body.occasion ?? "").trim();
  if (!relation || !occasion) {
    return NextResponse.json({ error: "Faltou dizer para quem e a ocasião." }, { status: 400 });
  }

  const payload: RequestPayload = {
    relation,
    ageRange: (body.ageRange ?? "").trim(),
    interests: Array.isArray(body.interests) ? body.interests.slice(0, 12) : [],
    freeText: (body.freeText ?? "").slice(0, 280).trim(),
    occasion,
    budgetId: body.budgetId,
    deadlineId: body.deadlineId ?? "sem-pressa",
  };

  const token = encodeToken(payload);

  if (isSupabaseConfigured()) {
    void persistForStats(payload, token).catch((err) =>
      console.error("[api/request] mesure non enregistrée:", err),
    );
  }

  return NextResponse.json({ token });
}

/** Écriture de mesure, en meilleur effort. Hors du chemin critique. */
async function persistForStats(payload: RequestPayload, token: string) {
  const budget = budgetById(payload.budgetId);
  const deadline = deadlineById(payload.deadlineId);

  const recipient = await createRecipient({
    nickname: null,
    relation: payload.relation,
    ageRange: payload.ageRange || null,
    interests: payload.interests,
    notes: payload.freeText || null,
  });

  await createRequest({
    id: requestKey(token),
    recipientId: recipient.id,
    occasion: payload.occasion,
    budgetMin: budget.min,
    budgetMax: budget.max,
    rawInput: payload.freeText || null,
    deadlineDays: deadline.days,
  });
}
