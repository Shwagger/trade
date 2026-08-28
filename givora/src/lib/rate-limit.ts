// ---------------------------------------------------------------------
// Rate limiting par IP, fenêtre glissante, en mémoire.
//
// LIMITE CONNUE : sur Vercel chaque instance a sa propre mémoire, donc
// la limite réelle est « N par instance », pas « N globalement ». C'est
// suffisant pour arrêter un script naïf qui brûle le budget API, pas
// pour un attaquant sérieux. Quand le trafic justifiera le coût, passer
// à un compteur partagé (table Postgres ou Upstash) : seule
// l'implémentation de `hit` change.
// ---------------------------------------------------------------------

type Window = { count: number; resetAt: number };

const g = globalThis as unknown as { __givoraRate?: Map<string, Window> };
const buckets: Map<string, Window> = g.__givoraRate ?? (g.__givoraRate = new Map());

const LIMIT = 12;              // demandes
const WINDOW_MS = 10 * 60_000; // par 10 minutes et par IP

export type RateResult = { allowed: boolean; retryAfterSeconds: number };

export function hit(ip: string): RateResult {
  const now = Date.now();
  const bucket = buckets.get(ip);

  if (!bucket || now > bucket.resetAt) {
    buckets.set(ip, { count: 1, resetAt: now + WINDOW_MS });
    if (buckets.size > 5000) sweep(now);
    return { allowed: true, retryAfterSeconds: 0 };
  }

  bucket.count += 1;
  if (bucket.count > LIMIT) {
    return { allowed: false, retryAfterSeconds: Math.ceil((bucket.resetAt - now) / 1000) };
  }
  return { allowed: true, retryAfterSeconds: 0 };
}

// Purge des fenêtres expirées : sans ça la Map grossit indéfiniment sur
// une instance à longue durée de vie.
function sweep(now: number) {
  for (const [key, w] of buckets) {
    if (now > w.resetAt) buckets.delete(key);
  }
}

/** L'IP réelle derrière le proxy Vercel. */
export function clientIp(req: Request): string {
  const forwarded = req.headers.get("x-forwarded-for");
  if (forwarded) return forwarded.split(",")[0].trim();
  return req.headers.get("x-real-ip") ?? "unknown";
}
