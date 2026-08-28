import { cookies } from "next/headers";

export const SESSION_COOKIE = "givora_sid";

/** L'id de visiteur posé par le middleware. Vide si le cookie manque. */
export async function sessionId(): Promise<string> {
  const jar = await cookies();
  return jar.get(SESSION_COOKIE)?.value ?? "";
}

/** Version route handler : lit le cookie sur la requête entrante. */
export function sessionIdFrom(req: Request): string {
  const header = req.headers.get("cookie") ?? "";
  const match = header.match(new RegExp(`(?:^|;\\s*)${SESSION_COOKIE}=([^;]+)`));
  return match ? decodeURIComponent(match[1]) : "";
}
