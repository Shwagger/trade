"use client";

import { MARKETPLACE_CTA } from "@/lib/constants";
import { visualFor } from "@/lib/visuals";
import type { Suggestion, VoteTally } from "@/lib/types";

export function SuggestionCard({
  suggestion,
  tally,
  href,
  onVote,
}: {
  suggestion: Suggestion;
  tally: VoteTally | undefined;
  /** Lien sortant, toujours via /go — jamais l'URL marchande. */
  href: string;
  onVote: (suggestionId: string, value: 1 | -1) => void;
}) {
  const cta = MARKETPLACE_CTA[suggestion.marketplace] ?? "Ver na loja";
  const visual = visualFor(suggestion.category, suggestion.glyph);
  const up = tally?.up ?? 0;
  const down = tally?.down ?? 0;
  const mine = tally?.mine ?? null;

  return (
    <article className="overflow-hidden rounded-3xl border-2 border-ink/10 bg-white shadow-sm">
      {/*
        L'illustration de la CATÉGORIE, pas une fausse photo de produit.
        Auto-hébergée : zéro requête, zéro licence, zéro image cassée.
        Quand un flux produit sera branché (src/lib/products.ts), la vraie
        photo prendra sa place ici sans rien changer d'autre.
      */}
      <a
        href={href}
        target="_blank"
        rel="sponsored nofollow noopener"
        aria-label={cta}
        className="flex h-36 items-center justify-center"
        style={{ background: `linear-gradient(135deg, ${visual.from}, ${visual.to})` }}
      >
        <span className="text-6xl drop-shadow-sm" aria-hidden>
          {visual.glyph}
        </span>
      </a>

      <div className="p-5">
      {/* Titre sur toute la largeur : à 390px, un badge à côté le casse
          en trois lignes. Prix et catégorie passent en dessous. */}
      <h2 className="text-xl font-bold leading-snug">{suggestion.title}</h2>

      <div className="mt-2 flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-mint/10 px-3 py-1 text-sm font-semibold text-mint">
          {suggestion.price_range}
        </span>
        <span className="text-xs font-semibold uppercase tracking-wide text-ink/35">
          {suggestion.category}
        </span>
      </div>

      <p className="mt-3 text-base leading-relaxed text-ink/75">
        <span className="font-semibold text-ink">Por que combina: </span>
        {suggestion.reason}
      </p>

      {/* Tous les liens sortants passent par /go : le clic est mesuré et
          l'URL affiliée n'apparaît jamais dans le HTML. */}
      <a href={href} target="_blank" rel="sponsored nofollow noopener" className="primary-btn mt-4">
        {cta}
      </a>

      {/* Le vote du groupe. C'est ce qui transforme un lien partagé dans
          le WhatsApp de la famille en conversation sur la page. */}
      <div className="mt-3 flex items-center gap-2">
        <VoteButton
          active={mine === 1}
          count={up}
          label="Curti essa"
          emoji="👍"
          onClick={() => onVote(suggestion.id, 1)}
        />
        <VoteButton
          active={mine === -1}
          count={down}
          label="Essa não"
          emoji="👎"
          onClick={() => onVote(suggestion.id, -1)}
        />
      </div>
      </div>
    </article>
  );
}

function VoteButton({
  active,
  count,
  label,
  emoji,
  onClick,
}: {
  active: boolean;
  count: number;
  label: string;
  emoji: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      aria-label={label}
      className={`flex min-h-[44px] flex-1 items-center justify-center gap-2 rounded-2xl border-2 text-base font-semibold transition active:scale-95 ${
        active ? "border-coral bg-coral/10 text-coral-dark" : "border-ink/10 bg-white text-ink/60"
      }`}
    >
      <span aria-hidden>{emoji}</span>
      <span className="tabular-nums">{count}</span>
    </button>
  );
}
