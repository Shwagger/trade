import { notFound } from "next/navigation";
import { ResultView } from "@/components/ResultView";
import { deadlineLabelFor } from "@/lib/constants";
import { budgetLabelFor, headlineFor } from "@/lib/headline";
import { sessionId } from "@/lib/session";
import { getRecipient, getRequest, getSuggestions, getTallies } from "@/lib/store";

// Rendu à la demande : la page dépend d'une ligne en base, pas du build.
export const dynamic = "force-dynamic";

export default async function ResultadoPage({
  params,
}: {
  params: Promise<{ requestId: string }>;
}) {
  const { requestId } = await params;

  const request = await getRequest(requestId);
  // Lien périmé ou id inventé : 404 propre, pas une page blanche.
  if (!request) notFound();

  const recipient = request.recipient_id ? await getRecipient(request.recipient_id) : null;

  // Si le moteur a déjà tourné pour cette demande (retour arrière, lien
  // partagé dans le groupe, refresh), on sert les cartes directement —
  // pas de skeleton, et surtout pas un deuxième appel API facturé.
  const [suggestions, sid] = await Promise.all([getSuggestions(requestId), sessionId()]);
  const tallies = suggestions.length > 0 ? await getTallies(requestId, sid) : [];

  return (
    <ResultView
      requestId={requestId}
      headline={headlineFor({
        relation: recipient?.relation ?? "outro",
        occasion: request.occasion,
        budget: budgetLabelFor(request.budget_min, request.budget_max),
      })}
      quote={request.raw_input}
      deadlineLabel={deadlineLabelFor(request.deadline_days)}
      initialSuggestions={suggestions}
      initialTallies={tallies}
    />
  );
}
