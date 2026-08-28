"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { StepShell } from "@/components/StepShell";
import {
  AGE_RANGES,
  BUDGETS,
  DEADLINES,
  INTEREST_CHIPS,
  OCCASIONS,
  RELATIONS,
  relationLabel,
} from "@/lib/constants";

// Tout l'état du formulaire tient dans ce composant : quatre useState et
// un index d'étape. Pas de store global — il n'y a rien à partager.

const TOTAL_STEPS = 4;

export default function Home() {
  const router = useRouter();
  const [step, setStep] = useState(1);

  const [relation, setRelation] = useState("");
  const [ageRange, setAgeRange] = useState("");
  const [interests, setInterests] = useState<string[]>([]);
  const [freeText, setFreeText] = useState("");
  const [occasion, setOccasion] = useState("");
  const [deadlineId, setDeadlineId] = useState("sem-pressa");

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggleInterest(chip: string) {
    setInterests((prev) =>
      prev.includes(chip) ? prev.filter((c) => c !== chip) : [...prev, chip],
    );
  }

  async function submit(budgetId: string) {
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch("/api/request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          relation, ageRange, interests, freeText, occasion, budgetId, deadlineId,
        }),
      });
      if (!res.ok) throw new Error("request failed");
      const { token } = (await res.json()) as { token: string };
      router.push(`/resultado/${token}`);
    } catch {
      setSubmitting(false);
      setError("Não deu para enviar agora. Toque de novo em alguns segundos.");
    }
  }

  // --- Étape 1 : la relation -----------------------------------------
  if (step === 1) {
    return (
      <StepShell
        step={1}
        total={TOTAL_STEPS}
        title="Quem vai ganhar o presente?"
        subtitle="Toque em quem chega mais perto."
      >
        <div className="grid grid-cols-2 gap-3">
          {RELATIONS.map((r) => (
            <button
              key={r.id}
              type="button"
              className={`touch-card !text-base ${relation === r.id ? "touch-card-selected" : ""}`}
              onClick={() => {
                setRelation(r.id);
                setStep(2);
              }}
            >
              <span className="text-2xl" aria-hidden>
                {r.emoji}
              </span>
              {r.label}
            </button>
          ))}
        </div>
      </StepShell>
    );
  }

  // --- Étape 2 : âge + centres d'intérêt ------------------------------
  if (step === 2) {
    const canContinue = ageRange !== "" && (interests.length > 0 || freeText.trim().length > 2);
    return (
      <StepShell
        step={2}
        total={TOTAL_STEPS}
        title="Quantos anos e o que essa pessoa curte?"
        subtitle="Quanto mais específico, melhor a sugestão."
        onBack={() => setStep(1)}
        footer={
          <button type="button" className="primary-btn" disabled={!canContinue} onClick={() => setStep(3)}>
            Continuar
          </button>
        }
      >
        <div className="space-y-6">
          <div>
            <p className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink/40">Idade</p>
            <div className="flex flex-wrap gap-2">
              {AGE_RANGES.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  className={`chip ${ageRange === a.id ? "chip-selected" : ""}`}
                  onClick={() => setAgeRange(a.id)}
                >
                  {a.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <label htmlFor="freeText" className="mb-2 block text-sm font-semibold uppercase tracking-wide text-ink/40">
              O que ela curte?
            </label>
            <textarea
              id="freeText"
              value={freeText}
              onChange={(e) => setFreeText(e.target.value)}
              rows={3}
              placeholder="Ex: ama café, corre no parque de manhã, tá sempre com o cachorro"
              className="w-full rounded-2xl border-2 border-ink/10 bg-white p-4 text-base outline-none focus:border-coral"
            />
          </div>

          <div>
            <p className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink/40">
              Ou toque no que combina
            </p>
            <div className="flex flex-wrap gap-2">
              {INTEREST_CHIPS.map((chip) => (
                <button
                  key={chip}
                  type="button"
                  className={`chip ${interests.includes(chip) ? "chip-selected" : ""}`}
                  onClick={() => toggleInterest(chip)}
                >
                  {chip}
                </button>
              ))}
            </div>
          </div>
        </div>
      </StepShell>
    );
  }

  // --- Étape 3 : l'occasion -------------------------------------------
  if (step === 3) {
    return (
      <StepShell
        step={3}
        total={TOTAL_STEPS}
        title="Qual é a ocasião?"
        onBack={() => setStep(2)}
      >
        <div className="space-y-3">
          {OCCASIONS.map((o) => (
            <button
              key={o.id}
              type="button"
              className={`touch-card ${occasion === o.id ? "touch-card-selected" : ""}`}
              onClick={() => {
                setOccasion(o.id);
                setStep(4);
              }}
            >
              <span className="text-2xl" aria-hidden>
                {o.emoji}
              </span>
              {o.label}
            </button>
          ))}
        </div>
      </StepShell>
    );
  }

  // --- Étape 4 : le budget (= envoi) ----------------------------------
  return (
    <StepShell
      step={4}
      total={TOTAL_STEPS}
      title="Quanto você quer gastar?"
      subtitle={`Vamos achar três ideias para ${relationLabel(relation).toLowerCase()}.`}
      onBack={() => setStep(3)}
    >
      {/* Le prazo tient sur le même écran que le budget : ce sont les
          deux contraintes dures, et un cinquième écran coûterait plus
          d'abandons qu'il ne rapporte. */}
      <div className="mb-6">
        <p className="mb-2 text-sm font-semibold uppercase tracking-wide text-ink/40">
          Precisa chegar até quando?
        </p>
        <div className="flex flex-wrap gap-2">
          {DEADLINES.map((d) => (
            <button
              key={d.id}
              type="button"
              className={`chip ${deadlineId === d.id ? "chip-selected" : ""}`}
              onClick={() => setDeadlineId(d.id)}
            >
              {d.label}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-3">
        {BUDGETS.map((b) => (
          <button
            key={b.id}
            type="button"
            disabled={submitting}
            className="touch-card justify-between disabled:opacity-50"
            onClick={() => submit(b.id)}
          >
            <span>{b.label}</span>
            <span className="text-sm font-normal text-ink/40">{b.hint}</span>
          </button>
        ))}
      </div>

      {submitting ? (
        <p className="mt-6 text-center text-base text-ink/60" aria-live="polite">
          Procurando ideias…
        </p>
      ) : null}
      {error ? (
        <p className="mt-6 text-center text-base text-coral-dark" role="alert">
          {error}
        </p>
      ) : null}
    </StepShell>
  );
}
