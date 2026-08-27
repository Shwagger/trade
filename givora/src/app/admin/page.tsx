import { cookies } from "next/headers";
import { affiliateStatus } from "@/lib/affiliates";
import { getAdminStats } from "@/lib/admin-stats";
import { MARKETPLACE_LABELS } from "@/lib/constants";
import { AdminLogin } from "./AdminLogin";

// Le mot de passe vit dans l'env, jamais dans le code. Sans ADMIN_PASSWORD
// configuré la page reste fermée : une page d'admin ouverte par défaut
// serait pire que pas d'admin du tout.
export const dynamic = "force-dynamic";

const AUTH_COOKIE = "givora_admin";

export default async function AdminPage({
  searchParams,
}: {
  searchParams: Promise<{ days?: string }>;
}) {
  const expected = process.env.ADMIN_PASSWORD ?? "";
  const jar = await cookies();
  const authorized = expected !== "" && jar.get(AUTH_COOKIE)?.value === expected;

  if (!authorized) {
    return <AdminLogin configured={expected !== ""} />;
  }

  const { days } = await searchParams;
  const window = days === "7" ? 7 : days === "30" ? 30 : 1;
  const stats = await getAdminStats(window);
  const affiliates = affiliateStatus();

  return (
    <div className="py-6">
      <header className="mb-6">
        <h1 className="text-2xl font-bold">Painel</h1>
        <div className="mt-3 flex gap-2">
          {[
            { d: 1, label: "Hoje" },
            { d: 7, label: "7 dias" },
            { d: 30, label: "30 dias" },
          ].map((o) => (
            <a
              key={o.d}
              href={`/admin?days=${o.d}`}
              className={`chip ${window === o.d ? "chip-selected" : ""}`}
            >
              {o.label}
            </a>
          ))}
        </div>
      </header>

      {!stats.live ? (
        <p className="mb-6 rounded-2xl border-2 border-coral/30 bg-white p-4 text-sm text-ink/70">
          Supabase não está configurado: o app está usando o store em memória e
          não há histórico para mostrar.
        </p>
      ) : null}

      {/* La métrique n°1 en premier et en gros. Tout le reste l'explique. */}
      <section className="rounded-3xl border-2 border-ink/10 bg-white p-6 text-center">
        <p className="text-sm font-semibold uppercase tracking-wide text-ink/40">
          Taxa de clique de saída
        </p>
        <p className="mt-2 text-5xl font-bold tabular-nums">
          {stats.clickRate === null ? "—" : `${(stats.clickRate * 100).toFixed(1)}%`}
        </p>
        <p className="mt-2 text-sm text-ink/50">
          {stats.clicks} clique(s) para {stats.sessions} sessão(ões)
        </p>
      </section>

      <section className="mt-4 grid grid-cols-2 gap-3">
        <Stat label="Sessões" value={stats.sessions} />
        <Stat label="Pedidos" value={stats.requests} />
        <Stat label="Cliques" value={stats.clicks} />
        <Stat
          label="Compartilhados"
          value={stats.shared}
          hint={stats.requests > 0 ? `${Math.round((stats.shared / stats.requests) * 100)}% dos pedidos` : undefined}
        />
      </section>

      <Section title="Por marketplace">
        {stats.byMarketplace.length === 0 ? (
          <Empty />
        ) : (
          <ul className="space-y-2">
            {stats.byMarketplace.map((m) => (
              <li key={m.marketplace} className="flex items-center justify-between text-base">
                <span>{MARKETPLACE_LABELS[m.marketplace] ?? m.marketplace}</span>
                <span className="font-semibold tabular-nums">{m.clicks}</span>
              </li>
            ))}
          </ul>
        )}
      </Section>

      <Section title="Sugestões mais clicadas">
        {stats.topSuggestions.length === 0 ? (
          <Empty />
        ) : (
          <ol className="space-y-3">
            {stats.topSuggestions.map((s, i) => (
              <li key={`${s.title}-${i}`} className="flex items-start justify-between gap-3 text-base">
                <span className="flex-1">
                  {s.title}
                  <span className="block text-xs uppercase tracking-wide text-ink/35">
                    {MARKETPLACE_LABELS[s.marketplace] ?? s.marketplace}
                  </span>
                </span>
                <span className="font-semibold tabular-nums">{s.clicks}</span>
              </li>
            ))}
          </ol>
        )}
      </Section>

      {/* Un lien affilié sans tag est du trafic offert gratuitement. */}
      <Section title="Programas de afiliação">
        <ul className="space-y-2">
          {affiliates.map((a) => (
            <li key={a.marketplace} className="flex items-center justify-between text-base">
              <span>{MARKETPLACE_LABELS[a.marketplace] ?? a.marketplace}</span>
              <span className={a.configured ? "font-semibold text-mint" : "font-semibold text-coral-dark"}>
                {a.configured ? "ativo" : `falta ${a.envVar}`}
              </span>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}

function Stat({ label, value, hint }: { label: string; value: number; hint?: string }) {
  return (
    <div className="rounded-2xl border-2 border-ink/10 bg-white p-4">
      <p className="text-xs font-semibold uppercase tracking-wide text-ink/40">{label}</p>
      <p className="mt-1 text-2xl font-bold tabular-nums">{value}</p>
      {hint ? <p className="text-xs text-ink/40">{hint}</p> : null}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-ink/40">{title}</h2>
      <div className="rounded-3xl border-2 border-ink/10 bg-white p-5">{children}</div>
    </section>
  );
}

function Empty() {
  return <p className="text-base text-ink/40">Nenhum clique ainda neste período.</p>;
}
