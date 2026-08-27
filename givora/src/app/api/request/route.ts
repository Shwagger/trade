import { NextResponse } from "next/server";
import { budgetById } from "@/lib/constants";
import { createRecipient, createRequest } from "@/lib/store";
import type { RequestPayload } from "@/lib/types";

// POST /api/request
// Enregistre le destinataire + la demande, renvoie l'id qui sert d'URL de
// résultat. Volontairement séparé de /api/recommend : on veut la demande
// en base même si le moteur échoue derrière — c'est la seule façon de
// mesurer les abandons.
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

  const budget = budgetById(body.budgetId);
  const interests = Array.isArray(body.interests) ? body.interests.slice(0, 20) : [];
  const freeText = (body.freeText ?? "").slice(0, 1000).trim();

  try {
    const recipient = await createRecipient({
      nickname: null,
      relation,
      ageRange: (body.ageRange ?? "").trim() || null,
      interests,
      notes: freeText || null,
    });

    const request = await createRequest({
      recipientId: recipient.id,
      occasion,
      budgetMin: budget.min,
      budgetMax: budget.max,
      rawInput: freeText || null,
    });

    return NextResponse.json({ requestId: request.id });
  } catch (err) {
    console.error("[api/request]", err);
    return NextResponse.json(
      { error: "Deu ruim aqui do nosso lado. Tente de novo." },
      { status: 500 },
    );
  }
}
