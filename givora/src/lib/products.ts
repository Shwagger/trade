import type { Marketplace } from "./types";

// =====================================================================
// PHOTOS ET LIENS PRODUIT RÉELS — la couche à brancher.
//
// Aujourd'hui cette fonction renvoie null : afficher la photo d'un
// produit précis suppose d'interroger le flux produit d'un marchand, et
// ça demande des identifiants qui appartiennent au propriétaire du site.
// Tant qu'elle renvoie null, les cartes montrent la tuile de catégorie
// (src/lib/visuals.ts) et le lien mène à une recherche filtrée par prix.
//
// COMMENT L'ALLUMER
//
// Mercado Livre — le plus accessible, et le seul qui couvre tout :
//   1. créer une application sur developers.mercadolivre.com.br (gratuit)
//   2. poser MERCADO_LIVRE_CLIENT_ID et MERCADO_LIVRE_CLIENT_SECRET
//   3. implémenter fetchFromMercadoLivre ci-dessous : échanger les
//      identifiants contre un token, appeler la recherche produit,
//      renvoyer le premier résultat pertinent dans la fourchette de prix
//
// Amazon (PA-API) exige 3 ventes qualifiantes avant de donner l'accès :
// ce n'est pas une option au démarrage. Shopee et Magalu passent par
// leurs propres programmes partenaires.
//
// À faire le jour où c'est branché : mettre en cache le résultat (le
// prix et le stock bougent, mais pas toutes les heures) et ne jamais
// bloquer le rendu de la page sur cet appel — une photo manquante doit
// dégrader vers la tuile, jamais faire attendre.
// =====================================================================

export type ResolvedProduct = {
  title: string;
  /** URL absolue de la photo du produit. */
  image: string;
  /** Prix réel constaté, en BRL. */
  price: number;
  /** Lien vers la fiche produit — pas vers une page de recherche. */
  url: string;
};

export function isProductFeedConfigured(): boolean {
  return Boolean(process.env.MERCADO_LIVRE_CLIENT_ID && process.env.MERCADO_LIVRE_CLIENT_SECRET);
}

export async function resolveProduct(
  _searchQuery: string,
  _marketplace: Marketplace,
  _budget: { min: number; max: number | null },
): Promise<ResolvedProduct | null> {
  if (!isProductFeedConfigured()) return null;

  // Non implémenté : les identifiants n'ont jamais été fournis, donc ce
  // code n'a jamais pu être exécuté ni testé une seule fois. Écrire un
  // appel HTTP que personne n'a vu tourner, c'est livrer une panne à
  // retardement — on renvoie null jusqu'à ce qu'on puisse le vérifier.
  console.warn("[products] identifiants présents mais résolution non implémentée");
  return null;
}
