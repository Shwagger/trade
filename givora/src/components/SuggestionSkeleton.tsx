// Jamais d'écran de chargement vide : on montre la forme des trois cartes
// plus une phrase qui dit ce qui se passe.
export function SuggestionSkeleton({ message }: { message: string }) {
  return (
    <div className="space-y-4" aria-busy="true" aria-live="polite">
      <p className="text-center text-base text-ink/60">{message}</p>
      {[0, 1, 2].map((i) => (
        <div key={i} className="animate-pulse rounded-3xl border-2 border-ink/5 bg-white p-5">
          {/* Même gabarit que SuggestionCard : rien ne bouge quand les
              vraies cartes arrivent. */}
          <div className="h-6 w-3/4 rounded-lg bg-ink/10" />
          <div className="mt-3 flex gap-2">
            <div className="h-7 w-28 rounded-full bg-ink/5" />
            <div className="h-7 w-20 rounded-full bg-ink/5" />
          </div>
          <div className="mt-4 h-4 w-full rounded bg-ink/5" />
          <div className="mt-2 h-4 w-4/5 rounded bg-ink/5" />
          <div className="mt-5 h-14 w-full rounded-2xl bg-ink/5" />
        </div>
      ))}
    </div>
  );
}
