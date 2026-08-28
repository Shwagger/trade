import type { Marketplace } from "./types";

// =====================================================================
// AFFILIATION — LE SEUL FICHIER À TOUCHER
//
// C'est ici que se trouve le revenu. Chaque marketplace a UNE entrée,
// avec son template d'URL et le nom de sa variable d'environnement.
//
// ⚠️ À VÉRIFIER À LA MAIN, programme par programme. Les formats
// ci-dessous viennent de la documentation publique de chaque programme
// et de l'usage courant, mais chaque programme d'affiliation a ses
// propres paramètres et les change sans prévenir. Ouvre ton panneau
// affilié, génère un lien de test, compare, et corrige la ligne
// concernée. Les lignes sont volontairement courtes et isolées pour que
// tu puisses en changer une sans toucher au reste.
//
// Degré de confiance, honnêtement :
//   - Amazon BR     : élevé  (`tag=` est le paramètre associé standard)
//   - Magalu        : élevé  (magazinevoce.com.br/magazine<TON_ID>/ est
//                             bien le format « Magalu Parceiro »)
//   - Mercado Livre : FAIBLE (le programme passe surtout par des liens
//                             générés dans le panneau ; `matt_tool` est
//                             le paramètre de tracking le plus courant)
//   - Shopee        : FAIBLE (Shopee Affiliate génère des shortlinks ;
//                             `af_id` est le paramètre habituel)
// =====================================================================

/** Fourchette de prix extraite de la suggestion, en reais entiers. */
export type PriceFilter = { min: number; max: number };

type AffiliateConfig = {
  /** Variable d'env qui porte l'identifiant affilié. */
  envVar: string;
  /**
   * Construit l'URL finale.
   * @param query  la requête de recherche, DÉJÀ encodée
   * @param tag    l'identifiant affilié ("" si non configuré)
   * @param price  la fourchette de prix, si connue
   */
  build: (query: string, tag: string, price: PriceFilter | null) => string;
};

export const AFFILIATES: Record<Marketplace, AffiliateConfig> = {
  // --- Amazon BR (Associados) ---------------------------------------
  // Le tag associé se passe en `tag=`. `low-price` / `high-price` filtrent
  // la page de résultats sur le budget : l'utilisateur atterrit sur des
  // produits qu'il peut vraiment acheter, pas sur du hors-budget.
  amazon_br: {
    envVar: "AMAZON_BR_TAG",
    build: (query, tag, price) => {
      const params = new URLSearchParams({ k: decodeURIComponent(query) });
      if (price) {
        params.set("low-price", String(price.min));
        params.set("high-price", String(price.max));
      }
      if (tag) params.set("tag", tag);
      return `https://www.amazon.com.br/s?${params.toString()}`;
    },
  },

  // --- Mercado Livre -------------------------------------------------
  // Le filtre de prix est dans le CHEMIN, pas en query string :
  //   /lista/QUERY_PriceRange_50-150
  // ⚠️ `matt_tool` est le paramètre de tracking le plus répandu, mais le
  // programme brésilien pousse plutôt des liens pré-générés : à confirmer
  // dans ton panneau avant de compter sur la commission.
  mercado_livre: {
    envVar: "MERCADO_LIVRE_TAG",
    build: (query, tag, price) => {
      const path = price ? `${query}_PriceRange_${price.min}-${price.max}` : query;
      const suffix = tag ? `?matt_tool=${encodeURIComponent(tag)}` : "";
      return `https://lista.mercadolivre.com.br/${path}${suffix}`;
    },
  },

  // --- Magalu (Magalu Parceiro / « Magazine Você ») -------------------
  // Le format affilié n'est PAS magazineluiza.com.br avec un paramètre :
  // c'est une boutique sur magazinevoce.com.br/magazine<TON_ID>/.
  // Sans identifiant configuré on retombe sur le site normal — le lien
  // marche, il ne rapporte simplement rien.
  magalu: {
    envVar: "MAGALU_TAG",
    build: (query, tag, price) => {
      const base = tag
        ? `https://www.magazinevoce.com.br/magazine${encodeURIComponent(tag)}`
        : "https://www.magazineluiza.com.br";
      const filter = price ? `?filtro=preco--${price.min}-${price.max}` : "";
      return `${base}/busca/${query}/${filter}`;
    },
  },

  // --- Shopee BR (Shopee Affiliate) ----------------------------------
  // `minPrice` / `maxPrice` filtrent la recherche. ⚠️ `af_id` est le
  // paramètre habituel, mais Shopee pousse surtout ses propres
  // shortlinks : à vérifier avant de compter sur la commission.
  shopee: {
    envVar: "SHOPEE_TAG",
    build: (query, tag, price) => {
      const params = new URLSearchParams({ keyword: decodeURIComponent(query) });
      if (price) {
        params.set("minPrice", String(price.min));
        params.set("maxPrice", String(price.max));
      }
      if (tag) params.set("af_id", tag);
      return `https://shopee.com.br/search?${params.toString()}`;
    },
  },
};

/**
 * Lit « R$ 70 - R$ 120 » et en sort { min: 70, max: 120 }.
 * Sans deux nombres exploitables on renvoie null : mieux vaut pas de
 * filtre qu'un filtre faux qui vide la page de résultats.
 */
export function parsePriceRange(priceRange: string): PriceFilter | null {
  const numbers = priceRange.match(/\d+/g)?.map(Number) ?? [];
  if (numbers.length < 2) return null;
  const min = Math.min(...numbers);
  const max = Math.max(...numbers);
  if (max <= min) return null;
  return { min, max };
}

/**
 * L'URL marchande finale, tag injecté.
 *
 * ⚠️ Cette URL ne doit JAMAIS partir dans le HTML servi au navigateur :
 * elle est construite dans /go/[suggestionId], côté serveur, juste avant
 * la redirection 302.
 */
export function buildAffiliateUrl(
  marketplace: Marketplace,
  searchQuery: string,
  priceRange?: string,
): string {
  const config = AFFILIATES[marketplace];
  const tag = (process.env[config.envVar] ?? "").trim();

  if (!tag) {
    // Pas bloquant, mais ça veut dire qu'on envoie du trafic gratuitement.
    console.warn(`[affiliates] ${config.envVar} non configuré — clic non monétisé`);
  }

  const price = priceRange ? parsePriceRange(priceRange) : null;
  return config.build(encodeURIComponent(searchQuery.trim()), tag, price);
}

/** Quels programmes sont réellement branchés. Affiché sur /admin. */
export function affiliateStatus(): {
  marketplace: Marketplace;
  envVar: string;
  configured: boolean;
}[] {
  return (Object.keys(AFFILIATES) as Marketplace[]).map((m) => ({
    marketplace: m,
    envVar: AFFILIATES[m].envVar,
    configured: Boolean((process.env[AFFILIATES[m].envVar] ?? "").trim()),
  }));
}
