import { NextResponse } from "next/server";
import { touchSession } from "@/lib/store";
import { sessionIdFrom } from "@/lib/session";

// POST /api/session
// Balise appelée une fois par chargement de page. C'est le dénominateur
// du taux de clic : sans sessions enregistrées, « 12 clics » ne veut
// rien dire.
//
// Le cookie est posé par le middleware ; la source utm est lue du cookie
// `givora_src` posé au même moment.
export async function POST(req: Request) {
  const sessionId = sessionIdFrom(req);
  if (!sessionId) return NextResponse.json({ ok: false });

  let source: Record<string, string> = {};
  const raw = req.headers.get("cookie")?.match(/(?:^|;\s*)givora_src=([^;]+)/);
  if (raw) {
    try {
      source = JSON.parse(decodeURIComponent(raw[1])) as Record<string, string>;
    } catch {
      // cookie corrompu : on enregistre la session sans source
    }
  }

  try {
    await touchSession({ sessionId, source });
  } catch (err) {
    console.error("[api/session]", err);
  }
  return NextResponse.json({ ok: true });
}
