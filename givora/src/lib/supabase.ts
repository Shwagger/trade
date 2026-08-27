import { createClient, type SupabaseClient } from "@supabase/supabase-js";

// Client serveur uniquement. La clé service_role ne doit JAMAIS partir dans
// un bundle client — ce fichier n'est importé que depuis des route handlers
// et des composants serveur.

let cached: SupabaseClient | null = null;

export function getSupabase(): SupabaseClient | null {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;

  // Pas de config = pas de Supabase. On ne casse pas l'app : le store
  // bascule sur sa version mémoire (voir src/lib/store.ts).
  if (!url || !key) return null;

  if (!cached) {
    cached = createClient(url, key, {
      auth: { persistSession: false, autoRefreshToken: false },
    });
  }
  return cached;
}

export function isSupabaseConfigured(): boolean {
  return getSupabase() !== null;
}
