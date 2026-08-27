import { NextResponse } from "next/server";
import { timingSafeEqual } from "node:crypto";

// Comparaison à temps constant : sur un mot de passe unique et partagé,
// une comparaison naïve laisse fuiter sa longueur et son préfixe.
function safeEqual(a: string, b: string): boolean {
  const bufA = Buffer.from(a);
  const bufB = Buffer.from(b);
  if (bufA.length !== bufB.length) return false;
  return timingSafeEqual(bufA, bufB);
}

export async function POST(req: Request) {
  const expected = process.env.ADMIN_PASSWORD ?? "";
  if (!expected) {
    return NextResponse.json({ error: "Painel desativado." }, { status: 403 });
  }

  let password = "";
  try {
    password = ((await req.json()) as { password?: string }).password ?? "";
  } catch {
    return NextResponse.json({ error: "JSON inválido." }, { status: 400 });
  }

  if (!safeEqual(password, expected)) {
    return NextResponse.json({ error: "Senha incorreta." }, { status: 401 });
  }

  const res = NextResponse.json({ ok: true });
  res.cookies.set("givora_admin", expected, {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 60 * 60 * 12, // une demi-journée : c'est un panneau, pas une session de travail
    path: "/",
  });
  return res;
}
