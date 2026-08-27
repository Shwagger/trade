"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { SuggestionCard } from "./SuggestionCard";
import { SuggestionSkeleton } from "./SuggestionSkeleton";
import type { Suggestion } from "@/lib/types";

const WAIT_MESSAGES = [
  "Lendo o que você contou…",
  "Separando três ideias diferentes…",
  "Conferindo se cabe no orçamento…",
];

export function ResultView({
  requestId,
  headline,
  initialSuggestions,
}: {
  requestId: string;
  headline: string;
  initialSuggestions: Suggestion[];
}) {
  const [suggestions, setSuggestions] = useState(initialSuggestions);
  const [loading, setLoading] = useState(initialSuggestions.length === 0);
  const [error, setError] = useState<string | null>(null);
  const [messageIndex, setMessageIndex] = useState(0);
  const [refineOpen, setRefineOpen] = useState(false);
  const [feedback, setFeedback] = useState("");

  // Le premier appel ne doit partir qu'une fois, même avec le double
  // montage du StrictMode en dev.
  const started = useRef(false);

  async function generate(withFeedback?: string) {
    setLoading(true);
    setError(null);
    setMessageIndex(0);
    try {
      const res = await fetch("/api/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ requestId, feedback: withFeedback }),
      });
      if (!res.ok) throw new Error("recommend failed");
      const data = (await res.json()) as { suggestions: Suggestion[] };
      setSuggestions(data.suggestions);
      setRefineOpen(false);
      setFeedback("");
    } catch {
      setError("Não conseguimos gerar as ideias agora. Toque para tentar de novo.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (started.current || initialSuggestions.length > 0) return;
    started.current = true;
    void generate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  const shareText = suggestions.length
    ? `Achei essas ideias de presente no Givora:\n\n${suggestions
        .map((s, i) => `${i + 1}. ${s.title} (${s.price_range})`)
        .join("\n")}`
    : "Achei o Givora, ele sugere presente em 30 segundos:";

  return (
    <div className="flex min-h-screen flex-col py-5">
      <header className="mb-6">
        <Link href="/" className="text-xl font-bold tracking-tight">
          Givora <span aria-hidden>🎁</span>
        </Link>
        <h1 className="mt-4 text-2xl font-bold leading-tight">Três ideias para você</h1>
        <p className="mt-1 text-base text-ink/60">{headline}</p>
      </header>

      <main className="flex-1 space-y-4">
        {loading ? (
          <SuggestionSkeleton message={WAIT_MESSAGES[messageIndex]} />
        ) : error ? (
          <div className="rounded-3xl border-2 border-coral/30 bg-white p-6 text-center">
            <p className="text-base text-ink/70" role="alert">
              {error}
            </p>
            <button type="button" className="primary-btn mt-4" onClick={() => generate()}>
              Tentar de novo
            </button>
          </div>
        ) : (
          suggestions.map((s) => <SuggestionCard key={s.id} suggestion={s} />)
        )}
      </main>

      {!loading && !error && suggestions.length > 0 ? (
        <div className="mt-6 space-y-3 pb-4">
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
                onClick={() => generate(feedback.trim())}
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
            className="flex min-h-[52px] w-full items-center justify-center rounded-2xl border-2 border-mint bg-mint/5 text-lg font-semibold text-mint active:scale-[0.98]"
          >
            💬 Mandar no WhatsApp
          </a>

          <Link href="/" className="block py-2 text-center text-base text-ink/50">
            Buscar para outra pessoa
          </Link>
        </div>
      ) : null}
    </div>
  );
}
