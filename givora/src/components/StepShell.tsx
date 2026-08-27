import { Progress } from "./Progress";

// Enveloppe commune aux 4 écrans : même position du titre, même barre de
// progression, même bouton retour. L'utilisateur ne doit jamais avoir
// l'impression de changer de site entre deux questions.
export function StepShell({
  step,
  total,
  title,
  subtitle,
  onBack,
  children,
  footer,
}: {
  step: number;
  total: number;
  title: string;
  subtitle?: string;
  onBack?: () => void;
  children: React.ReactNode;
  footer?: React.ReactNode;
}) {
  return (
    // key sur l'étape : React remonte le nœud à chaque question, donc
    // l'animation d'entrée se rejoue. Sans ça elle ne joue qu'une fois.
    <div key={step} className="screen-enter flex min-h-screen flex-col py-5">
      <header className="mb-6 space-y-4">
        <div className="flex items-center gap-3">
          {onBack ? (
            <button
              type="button"
              onClick={onBack}
              aria-label="Voltar"
              className="-ml-2 flex h-11 w-11 items-center justify-center rounded-full text-2xl active:bg-ink/5"
            >
              ←
            </button>
          ) : (
            <span className="text-xl font-bold tracking-tight">
              Givora <span aria-hidden>🎁</span>
            </span>
          )}
          <span className="ml-auto text-sm text-ink/40">
            {step} de {total}
          </span>
        </div>
        <Progress step={step} total={total} />
      </header>

      <h1 className="text-3xl font-bold leading-tight">{title}</h1>
      {subtitle ? <p className="mt-2 text-base text-ink/60">{subtitle}</p> : null}

      <div className="mt-6 flex-1">{children}</div>

      {footer ? <div className="sticky bottom-0 -mx-5 bg-cream px-5 pb-5 pt-3">{footer}</div> : null}
    </div>
  );
}
