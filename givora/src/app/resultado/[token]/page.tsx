import { notFound } from "next/navigation";
import { ResultView } from "@/components/ResultView";
import { budgetById, deadlineById, deadlineLabelFor } from "@/lib/constants";
import { budgetLabelFor, headlineFor } from "@/lib/headline";
import { suggestionsFromToken } from "@/lib/build-suggestions";
import { decodeToken, requestKey } from "@/lib/token";
import { sessionId } from "@/lib/session";
import { getTallies } from "@/lib/store";

// Rendu à la demande : la page dépend du jeton dans l'URL.
export const dynamic = "force-dynamic";

export default async function ResultadoPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;

  // Le lien CONTIENT la demande. Aucune base n'est interrogée pour
  // afficher la page — c'est ce qui rend le déploiement sans
  // configuration possible.
  const payload = decodeToken(token);
  if (!payload) notFound();

  const suggestions = suggestionsFromToken(token, payload);
  const budget = budgetById(payload.budgetId);
  const deadline = deadlineById(payload.deadlineId);

  // Les votes sont la seule chose qui a besoin d'un stockage partagé.
  // Sans Supabase la liste est vide et les boutons restent locaux :
  // dégradé, jamais cassé.
  const sid = await sessionId();
  const tallies = await getTallies(requestKey(token), sid).catch(() => []);

  return (
    <ResultView
      token={token}
      requestId={requestKey(token)}
      headline={headlineFor({
        relation: payload.relation,
        occasion: payload.occasion,
        budget: budgetLabelFor(budget.min, budget.max),
      })}
      quote={payload.freeText || null}
      deadlineLabel={deadlineLabelFor(deadline.days)}
      initialSuggestions={suggestions}
      initialTallies={tallies}
    />
  );
}
