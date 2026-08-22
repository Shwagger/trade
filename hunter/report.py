"""What the operator reads. Three outputs, one truth.

* ``render_run`` - the terminal report after a hunt: what came in, what is
  worth answering today, and what the market as a whole is asking for.
* ``render_market`` - the demand table on its own. This is the strategic
  output: after a week of hunting it says which service to standardise,
  based on counted posts instead of a guess.
* ``render_html`` - a one-file dashboard with the drafts one click from the
  clipboard, so the answering happens on a phone if needed.

The reports are written in French because the operator reads them; the drafts
they contain stay in the buyer's language.
"""

from __future__ import annotations

import html
import json
import time
from collections import Counter, defaultdict
from datetime import datetime
from statistics import median
from typing import Iterable, Optional

from .lead import Lead
from .offer import SYMBOL

BAR = "=" * 78

# Below this many qualified posts, a category ranking is noise dressed as a
# strategy. The whole point of counting demand is to stop guessing - reading a
# 4-post sample is guessing with extra steps.
MIN_SAMPLE = 15


# ----------------------------------------------------------------------
# market: what people actually asked for
# ----------------------------------------------------------------------
def market_table(leads: Iterable[Lead], days: float = 7.0) -> dict:
    """Counted demand per category over a window, with the money attached."""
    cutoff = time.time() - days * 86400
    rows = [lead for lead in leads
            if lead.tier != "IGNORE" and (not lead.created_utc or lead.created_utc >= cutoff)]
    per_category: dict[str, list[Lead]] = defaultdict(list)
    for lead in rows:
        per_category[lead.category].append(lead)

    table = []
    for key, group in per_category.items():
        budgets = [lead.budget["usd_high"] for lead in group
                   if lead.budget and lead.budget.get("per") == "project"]
        table.append({
            "category": key,
            "label": group[0].category_label or key,
            "count": len(group),
            "share": round(100 * len(group) / len(rows), 1) if rows else 0.0,
            "hot": sum(1 for lead in group if lead.tier == "HOT"),
            "median_budget": round(median(budgets)) if budgets else None,
            "with_budget": len(budgets),
        })
    table.sort(key=lambda row: (-row["count"], -(row["median_budget"] or 0)))
    return {"days": days, "analysed": len(rows), "rows": table,
            "sources": Counter(lead.source for lead in rows).most_common()}


def render_market(table: dict) -> str:
    lines = [BAR,
             f"CE QUE LE MARCHÉ DEMANDE  -  {table['analysed']} demandes retenues "
             f"sur {table['days']:.0f} jours",
             BAR]
    if not table["rows"]:
        lines.append("  rien encore. Lance quelques chasses avant de conclure quoi que ce soit.")
        return "\n".join(lines)
    lines.append(f"  {'catégorie':<28} {'part':>6} {'posts':>6} {'HOT':>4}  budget médian")
    for row in table["rows"]:
        bar = "#" * max(1, int(row["share"] / 4))
        budget = f"${row['median_budget']:,}" if row["median_budget"] else "n/c"
        lines.append(f"  {row['label']:<28} {row['share']:>5.1f}% {row['count']:>6} {row['hot']:>4}"
                     f"  {budget:<8} {bar}")
    top = table["rows"][0]
    runner_up = table["rows"][1]["count"] if len(table["rows"]) > 1 else 0
    lines.append("")
    if table["analysed"] < MIN_SAMPLE or top["count"] < 3:
        lines += [f"  -> échantillon trop petit pour conclure ({table['analysed']} demandes, "
                  f"il en faut ~{MIN_SAMPLE}).",
                  "     Continue de chasser avant de standardiser quoi que ce soit."]
    elif top["count"] == runner_up:
        lines += [f"  -> égalité entre {top['label']} et {table['rows'][1]['label']} "
                  f"({top['count']} demandes chacune).",
                  "     Prends celle où tu livres le plus vite, pas celle qui paie le mieux."]
    else:
        lines += [f"  -> le marché te dit de vendre : {top['label']} "
                  f"({top['count']} demandes, {top['hot']} chaudes)",
                  "     standardise cette offre avant d'en ajouter une deuxième."]
    return "\n".join(lines)


# ----------------------------------------------------------------------
# run report
# ----------------------------------------------------------------------
def render_run(leads: list[Lead], statuses: list, added: int, updated: int,
               show: int = 12, market_days: float = 7.0) -> str:
    now = datetime.now().strftime("%d/%m %H:%M")
    hot = [lead for lead in leads if lead.tier == "HOT"]
    warm = [lead for lead in leads if lead.tier == "WARM"]
    read = sum(status.count for status in statuses)
    ok = [status for status in statuses if status.ok]
    ko = [status for status in statuses if not status.ok]

    lines = [BAR,
             f"CHASSE  {now}   -  {read} posts lus, {added} nouveaux, "
             f"{len(hot)} HOT / {len(warm)} WARM",
             BAR, "", "SOURCES"]
    for status in ok:
        lines.append(f"  ok   {status.name:<34} {status.count:>4} posts")
    for status in ko:
        lines.append(f"  FAIL {status.name:<34} {status.detail}")
    if not statuses:
        lines.append("  (aucune source active)")

    for title, group in (("HOT - à traiter aujourd'hui", hot), ("WARM - si le HOT est vide", warm)):
        lines += ["", f"{title}  ({len(group)})"]
        if not group:
            lines.append("  rien. C'est normal certains jours — ne force pas une mauvaise offre.")
            continue
        lines.append(f"  {'id':<10} {'sc':>3} {'age':>6} {'budget':<22} {'prix':>7}  demande")
        for lead in group[:show]:
            budget = _budget_label(lead)
            price = f"${lead.price_usd:,.0f}" if lead.price_usd else "-"
            lines.append(f"  {lead.fingerprint:<10} {lead.score:>3} {lead.age_label():>6} "
                         f"{budget:<22} {price:>7}  {_short(lead.title, 46)}")
        if len(group) > show:
            lines.append(f"  ... et {len(group) - show} autres")

    lines += ["",
              "  python -m hunter draft <id>          le message prêt + le détail du score",
              "  python -m hunter mark <id> sent -n   quand tu l'as envoyé"]
    return "\n".join(lines)


def render_lead(lead: Lead, score_detail: str = "") -> str:
    """The full sheet for one lead: the post, the score, the price, the message."""
    lines = [BAR, f"{lead.tier}  {lead.score}/100   {lead.fingerprint}", BAR,
             f"  source     {lead.source}   ({lead.age_label()})",
             f"  lien       {lead.url}",
             f"  catégorie  {lead.category_label or lead.category}",
             f"  budget     {_budget_label(lead) or 'non annoncé'}",
             f"  délai      {(lead.deadline or {}).get('raw', 'non annoncé')}",
             f"  contact    {lead.contact}" + (f"  {lead.contact_address}" if lead.contact_address else ""),
             f"  statut     {lead.status}", ""]
    if score_detail:
        lines += ["POURQUOI CE SCORE", *[f"  {line}" for line in score_detail.splitlines()], ""]
    lines += ["LE POST", *[f"  {line}" for line in _wrap(lead.text, 74)[:18]], ""]
    lines += [f"PRIX  {_price_label(lead)}" if lead.price_usd else "PRIX  -",
              f"  {lead.price_note}", "",
              "MESSAGE (relis-le, adapte une ligne, envoie-le toi-même)",
              BAR, lead.draft, BAR]
    if lead.notes:
        lines += ["", "NOTES"]
        for note in lead.notes:
            stamp = datetime.fromtimestamp(note["at"]).strftime("%d/%m %H:%M")
            lines.append(f"  {stamp}  [{note['status']}] {note['note']}")
    return "\n".join(lines)


def render_funnel(funnel: dict, wins: list[Lead]) -> str:
    counts = funnel["counts"]
    lines = [BAR, "PIPELINE", BAR,
             f"  trouvés     {funnel['total']:>4}",
             f"  envoyés     {funnel['sent']:>4}",
             f"  répondus    {counts['replied'] + counts['won']:>4}"
             + (f"   ({funnel['reply_rate']}% des envois)" if funnel["reply_rate"] is not None else ""),
             f"  gagnés      {counts['won']:>4}"
             + (f"   ({funnel['win_rate']}% des envois)" if funnel["win_rate"] is not None else ""),
             f"  morts       {counts['dead']:>4}"]
    if wins:
        lines += ["", "POURQUOI ILS ONT PAYÉ  (la seule donnée qui compte)"]
        for lead in wins:
            note = lead.notes[-1]["note"] if lead.notes else "(aucune note — ajoutes-en une)"
            lines.append(f"  {lead.category_label:<24} ${lead.price_usd or 0:,.0f}  {note}")
    elif funnel["sent"]:
        lines += ["", "  aucune vente encore. Regarde les messages envoyés : trop long ? "
                      "prix flou ? pas de preuve gratuite ?"]
    return "\n".join(lines)


def format_telegram(leads: list[Lead]) -> str:
    """Short enough to read on a phone, complete enough to act on."""
    if not leads:
        return "Chasse terminee : aucun lead HOT."
    lines = [f"{len(leads)} lead(s) HOT"]
    for lead in leads[:5]:
        budget = _budget_label(lead) or "budget n/c"
        lines += ["", f"[{lead.score}] {_short(lead.title, 90)}",
                  f"{budget} | prix conseillé ${lead.price_usd or 0:,.0f} | {lead.age_label()}",
                  lead.url, f"id {lead.fingerprint}"]
    return "\n".join(lines)


# ----------------------------------------------------------------------
# html dashboard
# ----------------------------------------------------------------------
def render_html(leads: list[Lead], market: dict, funnel: dict, demo: Optional[bool] = None) -> str:
    """``demo`` defaults to whatever the data says: any synthetic lead flags the page."""
    if demo is None:
        demo = any(lead.extra.get("synthetic") for lead in leads)
    cards = "\n".join(_card(lead) for lead in leads if lead.tier != "IGNORE") or (
        '<p class="empty">Aucune demande retenue pour l\'instant.</p>')
    rows = "\n".join(
        f'<tr><td>{html.escape(row["label"])}</td><td class="num">{row["count"]}</td>'
        f'<td class="num">{row["share"]:.0f}%</td><td class="num">{row["hot"]}</td>'
        f'<td class="num">{("$" + format(row["median_budget"], ",")) if row["median_budget"] else "-"}</td></tr>'
        for row in market["rows"]) or '<tr><td colspan="5">-</td></tr>'
    banner = ('<div class="banner">DEMO - ces annonces sont synthétiques, personne ne les a '
              'ecrites. Elles servent à vérifier le pipeline.</div>' if demo else "")
    return _HTML.replace("{{banner}}", banner).replace("{{cards}}", cards).replace(
        "{{rows}}", rows).replace("{{stamp}}", datetime.now().strftime("%d/%m/%Y %H:%M")).replace(
        "{{hot}}", str(sum(1 for lead in leads if lead.tier == "HOT"))).replace(
        "{{warm}}", str(sum(1 for lead in leads if lead.tier == "WARM"))).replace(
        "{{sent}}", str(funnel["sent"])).replace("{{won}}", str(funnel["counts"]["won"]))


def _card(lead: Lead) -> str:
    budget = html.escape(_budget_label(lead) or "budget non annoncé")
    signals = " ".join(
        f'<span class="sig">{html.escape(item["name"])}</span>' for item in lead.signals[:5])
    return f"""
<article class="lead {lead.tier.lower()}" data-tier="{lead.tier}">
  <header>
    <span class="score">{lead.score}</span>
    <div>
      <h3>{html.escape(_short(lead.title, 110))}</h3>
      <p class="meta">{html.escape(lead.source)} · {lead.age_label()} · {html.escape(lead.category_label or lead.category)} · {budget}</p>
    </div>
  </header>
  <p class="sigs">{signals}</p>
  <p class="price">Prix conseillé <strong>{html.escape(_price_label(lead))}</strong> — <span>{html.escape(lead.price_note)}</span></p>
  <details><summary>Le message à envoyer</summary><pre id="d-{lead.fingerprint}">{html.escape(lead.draft)}</pre>
    <button onclick="copy('d-{lead.fingerprint}',this)">Copier</button>
    <a href="{html.escape(lead.url)}" target="_blank" rel="noopener">Ouvrir l'annonce</a>
    <code>python -m hunter mark {lead.fingerprint} sent</code>
  </details>
</article>"""


_HTML = """<title>Demand Hunter</title>
<style>
:root{--bg:#f7f7f5;--fg:#1c1b19;--muted:#6b6a66;--card:#fff;--line:#e2e0da;--hot:#c2410c;--warm:#a16207;--accent:#1c1b19}
:root:not([data-theme="light"]){}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#16151300;--bg:#161513;--fg:#f0eee8;--muted:#a3a099;--card:#211f1d;--line:#33302c;--hot:#fb923c;--warm:#fbbf24;--accent:#f0eee8}}
:root[data-theme="dark"]{--bg:#161513;--fg:#f0eee8;--muted:#a3a099;--card:#211f1d;--line:#33302c;--hot:#fb923c;--warm:#fbbf24;--accent:#f0eee8}
*{box-sizing:border-box}
body{margin:0;padding:24px 16px 64px;background:var(--bg);color:var(--fg);font:15px/1.5 ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:900px;margin:0 auto}
h1{font-size:24px;margin:0 0 4px}
.stamp{color:var(--muted);font-size:13px;margin:0 0 20px}
.banner{background:var(--warm);color:#161513;padding:10px 14px;border-radius:8px;font-weight:600;margin-bottom:18px}
.kpis{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:22px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 16px;min-width:96px}
.kpi b{display:block;font-size:22px}
.kpi span{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
.filters{display:flex;gap:8px;margin-bottom:14px}
button{font:inherit;background:var(--card);color:var(--fg);border:1px solid var(--line);border-radius:8px;padding:6px 12px;cursor:pointer}
button.on{background:var(--accent);color:var(--bg)}
.lead{background:var(--card);border:1px solid var(--line);border-left:4px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:12px}
.lead.hot{border-left-color:var(--hot)}.lead.warm{border-left-color:var(--warm)}
.lead header{display:flex;gap:14px;align-items:flex-start}
.score{font-size:26px;font-weight:700;min-width:46px;text-align:center}
.lead.hot .score{color:var(--hot)}.lead.warm .score{color:var(--warm)}
h3{margin:0 0 2px;font-size:16px;font-weight:600}
.meta{margin:0;color:var(--muted);font-size:13px}
.sigs{margin:10px 0 6px;display:flex;flex-wrap:wrap;gap:6px}
.sig{background:var(--bg);border:1px solid var(--line);border-radius:99px;padding:2px 9px;font-size:12px;color:var(--muted)}
.price{margin:6px 0;font-size:14px}.price span{color:var(--muted)}
details{margin-top:8px}summary{cursor:pointer;font-weight:600}
pre{white-space:pre-wrap;background:var(--bg);border:1px solid var(--line);border-radius:8px;padding:12px;margin:10px 0;font:13px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;overflow-x:auto}
details a{margin-left:10px}details code{margin-left:10px;color:var(--muted);font-size:12px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{padding:8px 12px;text-align:left;border-bottom:1px solid var(--line);font-size:14px}
th{color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.04em}
td.num{text-align:right}
h2{font-size:15px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);margin:32px 0 10px}
.empty{color:var(--muted)}
</style>
<div class="wrap">
{{banner}}
<h1>Demand Hunter</h1>
<p class="stamp">dernière chasse : {{stamp}}</p>
<div class="kpis">
  <div class="kpi"><b>{{hot}}</b><span>hot</span></div>
  <div class="kpi"><b>{{warm}}</b><span>warm</span></div>
  <div class="kpi"><b>{{sent}}</b><span>envoyés</span></div>
  <div class="kpi"><b>{{won}}</b><span>gagnés</span></div>
</div>
<div class="filters">
  <button class="on" onclick="filter('ALL',this)">Tout</button>
  <button onclick="filter('HOT',this)">HOT</button>
  <button onclick="filter('WARM',this)">WARM</button>
</div>
{{cards}}
<h2>Ce que le marché demande</h2>
<table><tr><th>catégorie</th><th class="num">posts</th><th class="num">part</th><th class="num">hot</th><th class="num">budget médian</th></tr>
{{rows}}
</table>
</div>
<script>
function filter(tier,btn){
  document.querySelectorAll('.filters button').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
  document.querySelectorAll('.lead').forEach(el=>{
    el.style.display = (tier==='ALL'||el.dataset.tier===tier) ? '' : 'none';
  });
}
function copy(id,btn){
  const text=document.getElementById(id).innerText;
  navigator.clipboard.writeText(text).then(()=>{btn.textContent='Copie';setTimeout(()=>btn.textContent='Copier',1500)})
   .catch(()=>{btn.textContent='Sélectionne et copie à la main'});
}
</script>"""


# ----------------------------------------------------------------------
def _price_label(lead: Lead) -> str:
    """The price as the client will read it, with the USD behind it for you."""
    if lead.price_usd is None:
        return "-"
    usd = f"${lead.price_usd:,.0f}"
    if not lead.price_display or lead.price_display == usd:
        return usd
    return f"{lead.price_display}  (~{usd})"


def _budget_label(lead: Lead) -> str:
    """As the poster wrote it, with the USD equivalent so leads stay comparable."""
    if not lead.budget:
        return ""
    budget = lead.budget
    unit = "/h" if budget.get("per") == "hour" else ""
    symbol = SYMBOL.get(budget["currency"], f"{budget['currency']} ")
    low, high = budget["low"], budget["high"]
    written = (f"{symbol}{low:,.0f}{unit}" if low == high
               else f"{symbol}{low:,.0f}-{high:,.0f}{unit}")
    if budget["currency"] == "USD":
        return written
    usd = budget["usd_high"]
    return f"{written} (~${usd:,.0f})"


def _short(text: str, width: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= width else text[: width - 1] + "…"


def _wrap(text: str, width: int) -> list[str]:
    out: list[str] = []
    for paragraph in (text or "").split("\n"):
        line = ""
        for word in paragraph.split():
            if len(line) + len(word) + 1 > width:
                out.append(line)
                line = word
            else:
                line = f"{line} {word}".strip()
        out.append(line)
    return out
