import { NextResponse } from "next/server";
import { markShared } from "@/lib/store";

// POST /api/share { requestId }
// Marque qu'un lien a réellement été partagé. Sans cette mesure, on ne
// saura jamais si la boucle WhatsApp existe ou si on se raconte une
// histoire. Volontairement silencieux : ça ne doit jamais bloquer le
// partage lui-même.
export async function POST(req: Request) {
  try {
    const { requestId } = (await req.json()) as { requestId?: string };
    if (requestId) await markShared(requestId);
  } catch (err) {
    console.error("[api/share]", err);
  }
  return NextResponse.json({ ok: true });
}
