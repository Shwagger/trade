"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { SuggestionCard } from "./SuggestionCard";
import { SuggestionSkeleton } from "./SuggestionSkeleton";
import type { Suggestion, VoteTally } from "@/lib/types";

const WAIT_MESSAGES = [
  "Lendo o que você contou…",
  "Separando três ideias diferentes…",
  "Conferindo se cabe no orçamento…",
];

export function ResultView({
  token,
  requestId,
  headline,
  quote,
  deadlineLabel,
  initialSuggestions,
  initialTallies,
}: {
  /** Le jeton porte la demande : il sert à reconstruire les liens /go. */
  token: string;
  requestId: string;
  headline: string;
  /** Les mots exacts de l'utilisateur. On les lui rend pour prouver qu'on a lu. */
  quote: string | null;
  deadlineLabel: string | null;
  initialSuggestions: Suggestion[];
  initialTallies: VoteTally[];
}) {
  // Les cartes viennent du serveur, calculées depuis le jeton : il n'y a
  // plus rien à charger à l'ouverture. `loading` ne sert qu'au temps de
  // la navigation vers un résultat affiné.
  const suggestions = initialSuggestions;
  const [tallies, setTallies] = useState(initialTallies);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [messageIndex, setMessageIndex] = useState(0);
  const [refineOpen, setRefineOpen] = useState(false);
  const [feedback, setFeedback] = useState("");

  const router = useRouter();

  // Le « refinar » ne recalcule rien ici : il demande un nouveau JETON et
  // navigue dessus. Le résultat affiné est donc lui aussi une URL
  // partageable, identique pour tous ceux qui l'ouvriront.
  const refine = useCallback(
    async (withFeedback: string) => {
      setLoading(true);
      setError(null);
      setMessageIndex(0);
      try {
        const res = await fetch("/api/refine", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ token, feedback: withFeedback }),
        });
        const data = (await res.json()) as { token?: string; error?: string };
        if (!res.ok || !data.token) throw new Error(data.error ?? "falha");
        router.push(`/resultado/${data.token}`);
      } catch (err) {
        setLoading(false);
        setError(
          err instanceof Error && err.message !== "falha"
            ? err.message
            : "Não conseguimos gerar outras ideias agora. Toque para tentar de novo.",
        );
      }
    },
    [token, router],
  );


  // Le message d'attente change toutes les 1,8 s : l'utilisateur voit que
  // quelque chose bouge même si la réponse prend 6 secondes.
  useEffect(() => {
    if (!loading) return;
    const t = setInterval(
      () => setMessageIndex((i) => Math.min(i + 1, WAIT_MESSAGES.length - 1)),
      1800,
    );
    return () => clearInterval(t);
  }, [loading]);

  // Le groupe vote pendant que la page est ouverte : on relit les votes
  // au retour au premier plan, pas en boucle — personne ne veut d'un
  // polling qui vide la batterie.
  useEffect(() => {
    if (suggestions.length === 0) return;
    const refresh = async () => {
      if (document.visibilityState !== "visible") return;
      try {
        const res = await fetch(`/api/vote?requestId=${requestId}`);
        if (res.ok) setTallies(((await res.json()) as { tallies: VoteTally[] }).tallies);
      } catch {
        // silencieux : un décompte périmé n'est pas une erreur à montrer
      }
    };
    document.addEventListener("visibilitychange", refresh);
    return () => document.removeEventListener("visibilitychange", refresh);
  }, [requestId, suggestions.length]);

  async function vote(suggestionId: string, value: 1 | -1) {
    // Optimiste : le compteur bouge tout de suite, le serveur confirme.
    setTallies((prev) => {
      const next = prev.filter((t) => t.suggestion_id !== suggestionId);
      const current = prev.find((t) => t.suggestion_id === suggestionId) ?? {
        suggestion_id: suggestionId, up: 0, down: 0, mine: null as -1 | 1 | null,
      };
      const wasUp = current.mine === 1;
      const wasDown = current.mine === -1;
      return [...next, {
        suggestion_id: suggestionId,
        up: current.up - (wasUp ? 1 : 0) + (value === 1 ? 1 : 0),
        down: current.down - (wasDown ? 1 : 0) + (value === -1 ? 1 : 0),
        mine: value,
      }];
    });

    try {
      const res = await fetch("/api/vote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ requestId, suggestionId, value }),
      });
      if (res.ok) setTallies(((await res.json()) as { tallies: VoteTally[] }).tallies);
    } catch {
      // le vote optimiste reste affiché ; le prochain refresh corrigera
    }
  }

  const shareUrl = typeof window !== "undefined" ? window.location.href : "";
  const shareText = suggestions.length
    ? `Achei essas ideias de presente:\n\n${suggestions
        .map((s, i) => `${i + 1}. ${s.title} (${s.price_range})`)
        .join("\n")}\n\nQual vocês acham? Vota aí 👇\n${shareUrl}`
    : "Achei o Givora, ele sugere presente em 30 segundos:";

  function trackShare() {
    // keepalive : la navigation vers WhatsApp ne doit pas tuer la mesure.
    void fetch("/api/share", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ requestId }),
      keepalive: true,
    }).catch(() => {});
  }

  const talliesById = new Map(tallies.map((t) => [t.suggestion_id, t]));
  const votesCast = tallies.reduce((n, t) => n + t.up + t.down, 0);

  return (
    <div className="flex min-h-screen flex-col py-5">
      <header className="mb-6">
        <Link href="/" className="text-xl font-bold tracking-tight">
          Givora <span aria-hidden>🎁</span>
        </Link>
        <h1 className="mt-4 text-2xl font-bold leading-tight">Três ideias para você</h1>
        <p className="mt-1 text-base text-ink/60">{headline}</p>

        {deadlineLabel ? (
          <p className="mt-2 inline-block rounded-full bg-coral/10 px-3 py-1 text-sm font-semibold text-coral-dark">
            ⏱ {deadlineLabel}
          </p>
        ) : null}

        {/* Ses propres mots, renvoyés tels quels. C'est la preuve en une
            seconde qu'on a lu ce qu'il a écrit — et c'est exactement ce
            que les concurrents ne font pas. */}
        {quote ? (
          <blockquote className="mt-4 border-l-4 border-coral/40 pl-4 text-base italic leading-relaxed text-ink/70">
            “{quote}”
          </blockquote>
        ) : null}
      </header>

      <main className="flex-1 space-y-4">
        {loading ? (
          <SuggestionSkeleton message={WAIT_MESSAGES[messageIndex]} />
        ) : error ? (
          <div className="rounded-3xl border-2 border-coral/30 bg-white p-6 text-center">
            <p className="text-base text-ink/70" role="alert">
              {error}
            </p>
            <button type="button" className="primary-btn mt-4" onClick={() => setError(null)}>
              Tentar de novo
            </button>
          </div>
        ) : (
          suggestions.map((s) => (
            <SuggestionCard
              key={s.id}
              suggestion={s}
              tally={talliesById.get(s.id)}
              href={`/go/${token}/${s.position}`}
              onVote={vote}
            />
          ))
        )}
      </main>

      {!loading && !error && suggestions.length > 0 ? (
        <div className="mt-6 space-y-3 pb-4">
          {votesCast > 0 ? (
            <p className="text-center text-sm text-ink/50">
              {votesCast} {votesCast === 1 ? "voto" : "votos"} até agora
            </p>
          ) : null}

          {refineOpen ? (
            <div className="rounded-3xl border-2 border-ink/10 bg-white p-4">
              <label htmlFor="feedback" className="text-sm font-semibold text-ink/60">
                O que não encaixou?
              </label>
              <textarea
                id="feedback"
                rows={2}
                value={feedback}
                onChange={(e) => setFeedback(e.target.value)}
                placeholder="Ex: ela já tem fone, prefiro algo para a casa"
                className="mt-2 w-full rounded-2xl border-2 border-ink/10 p-3 text-base outline-none focus:border-coral"
              />
              <button
                type="button"
                className="primary-btn mt-3"
                disabled={feedback.trim().length < 3}
                onClick={() => void refine(feedback.trim())}
              >
                Gerar outras três
              </button>
            </div>
          ) : (
            <button
              type="button"
              className="flex min-h-[52px] w-full items-center justify-center rounded-2xl border-2 border-ink/15 bg-white text-lg font-semibold active:scale-[0.98]"
              onClick={() => setRefineOpen(true)}
            >
              🔄 Refinar as sugestões
            </button>
          )}

          <a
            href={`https://wa.me/?text=${encodeURIComponent(shareText)}`}
            target="_blank"
            rel="noopener noreferrer"
            onClick={trackShare}
            className="flex min-h-[52px] w-full items-center justify-center rounded-2xl border-2 border-mint bg-mint/5 text-lg font-semibold text-mint active:scale-[0.98]"
          >
            💬 Perguntar no WhatsApp
          </a>

          <Link href="/" className="block py-2 text-center text-base text-ink/50">
            Buscar para outra pessoa
          </Link>
        </div>
      ) : null}
    </div>
  );
}
