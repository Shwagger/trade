"""Command line interface.

    python -m hunter hunt --demo            # offline run on synthetic posts
    python -m hunter hunt                   # the real thing: fetch, score, prepare
    python -m hunter hunt --html out.html --telegram
    python -m hunter list --tier HOT
    python -m hunter draft a1b2c3d4         # the message + why the score is what it is
    python -m hunter mark a1b2c3d4 sent -n "envoye en DM"
    python -m hunter pipeline               # trouvés -> envoyés -> répondus -> gagnes
    python -m hunter market --days 14       # what to sell, counted not guessed

Nothing here contacts a lead. The last step is always a human pressing send.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import DEFAULT_WORKDIR, __version__
from .intent import explain, qualify
from .lead import STATUSES
from .offer import LANGS, polish, prepare
from .report import (format_telegram, market_table, render_funnel, render_html, render_lead,
                     render_market, render_run)
from .sources import fetch_demo, load_config, run_sources
from .store import Store


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m hunter",
        description="AI Demand Hunter - trouve les gens qui ont déjà demandé à payer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    parser.add_argument("--version", action="version", version=f"hunter {__version__}")
    parser.add_argument("--workdir", default=DEFAULT_WORKDIR, help="où vivent les leads")
    sub = parser.add_subparsers(dest="command", required=True)

    hunt = sub.add_parser("hunt", help="chercher, qualifier, préparer les messages")
    hunt.add_argument("--demo", action="store_true",
                      help="tourne hors ligne sur des annonces synthétiques")
    hunt.add_argument("--config", default="config/hunter.json")
    hunt.add_argument("--sources", default="", help="reddit,hn,remoteok,rss (défaut : la config)")
    hunt.add_argument("--rate", type=float, default=1.5, help="secondes entre deux requêtes")
    hunt.add_argument("--lang", default="en", choices=LANGS, help="langue des messages")
    hunt.add_argument("--llm", action="store_true", help="repasser les messages HOT via Ollama")
    hunt.add_argument("--html", default="", help="écrire le tableau de bord ici")
    hunt.add_argument("--telegram", action="store_true", help="alerter sur les leads HOT")
    hunt.add_argument("--show", type=int, default=12)
    hunt.add_argument("--market-days", type=float, default=7.0)

    listing = sub.add_parser("list", help="lister les leads déjà trouvés")
    listing.add_argument("--tier", choices=["HOT", "WARM", "IGNORE"])
    listing.add_argument("--status", choices=list(STATUSES))
    listing.add_argument("--category", default=None)
    listing.add_argument("--min-score", type=int, default=0)
    listing.add_argument("--max-age-hours", type=float, default=None)
    listing.add_argument("--limit", type=int, default=25)
    listing.add_argument("--json", action="store_true")

    draft = sub.add_parser("draft", help="la fiche complète d'un lead + le message")
    draft.add_argument("id")
    draft.add_argument("--lang", default=None, choices=LANGS, help="régénérer dans cette langue")
    draft.add_argument("--llm", action="store_true", help="repasser le message via Ollama")

    mark = sub.add_parser("mark", help="mettre à jour le statut d'un lead")
    mark.add_argument("id")
    mark.add_argument("status", choices=list(STATUSES))
    mark.add_argument("-n", "--note", default="")

    sub.add_parser("pipeline", help="le tunnel : envoyés, répondus, gagnés")

    market = sub.add_parser("market", help="ce que le marché demande, compté")
    market.add_argument("--days", type=float, default=7.0)

    dashboard = sub.add_parser("html", help="régénérer le tableau de bord sans rechasser")
    dashboard.add_argument("--out", default="state/hunter/dashboard.html")
    dashboard.add_argument("--market-days", type=float, default=7.0)

    sub.add_parser("sources", help="état des sources au dernier passage")
    return parser


# ----------------------------------------------------------------------
def cmd_hunt(args) -> int:
    store = Store(args.workdir)
    if args.demo:
        result = fetch_demo()
    else:
        config = load_config(args.config)
        only = [name.strip() for name in args.sources.split(",") if name.strip()] or None
        result = run_sources(config, only, args.rate)

    for lead in result.leads:
        prepare(qualify(lead), args.lang)

    report = store.upsert(result.leads)
    if args.llm:
        for lead in store.select(tier="HOT", status="new"):
            lead.draft = polish(lead.draft)
    store.save()
    store.record_run(result.statuses, report)

    leads = store.all()
    print(render_run(leads, result.statuses, report.added, report.updated,
                     args.show, args.market_days))
    print()
    print(render_market(market_table(leads, args.market_days)))

    if args.html:
        _write_html(args.html, store, args.market_days)
        print(f"\ntableau de bord -> {args.html}")

    if args.telegram:
        _telegram(store.select(tier="HOT", status="new", limit=5))
    return 0


def cmd_list(args) -> int:
    store = Store(args.workdir)
    rows = store.select(tier=args.tier, status=args.status, category=args.category,
                        min_score=args.min_score, max_age_hours=args.max_age_hours,
                        limit=args.limit)
    if args.json:
        print(json.dumps([lead.to_dict() for lead in rows], ensure_ascii=False, indent=2))
        return 0
    if not rows:
        print("aucun lead ne correspond.")
        return 0
    print(f"{'id':<10} {'tier':<6} {'sc':>3} {'age':>6} {'statut':<8} {'catégorie':<26} titre")
    for lead in rows:
        print(f"{lead.fingerprint:<10} {lead.tier:<6} {lead.score:>3} {lead.age_label():>6} "
              f"{lead.status:<8} {(lead.category_label or lead.category)[:26]:<26} "
              f"{lead.title[:52]}")
    return 0


def cmd_draft(args) -> int:
    store = Store(args.workdir)
    lead = store.get(args.id)
    if lead is None:
        print(f"aucun lead avec l'id « {args.id} ». `python -m hunter list` pour les voir.")
        return 1
    if args.lang:
        prepare(lead, args.lang)
    if args.llm:
        lead.draft = polish(lead.draft)
    if args.lang or args.llm:
        store.save()
    print(render_lead(lead, explain(lead)))
    return 0


def cmd_mark(args) -> int:
    store = Store(args.workdir)
    lead = store.mark(args.id, args.status, args.note)
    if lead is None:
        print(f"aucun lead avec l'id « {args.id} ».")
        return 1
    print(f"{lead.fingerprint} -> {lead.status}")
    if args.status == "won" and not args.note:
        print("ajoute une note (-n) : pourquoi il a paye est la seule donnée qui compte.")
    return 0


def cmd_pipeline(args) -> int:
    store = Store(args.workdir)
    print(render_funnel(store.funnel(), store.wins()))
    return 0


def cmd_market(args) -> int:
    store = Store(args.workdir)
    print(render_market(market_table(store.all(), args.days)))
    return 0


def cmd_html(args) -> int:
    store = Store(args.workdir)
    _write_html(args.out, store, args.market_days)
    print(f"tableau de bord -> {args.out}")
    return 0


def cmd_sources(args) -> int:
    store = Store(args.workdir)
    run = store.last_run()
    if not run:
        print("aucune chasse enregistrée. Lance `python -m hunter hunt --demo` pour tester.")
        return 0
    from datetime import datetime

    print(f"dernière chasse : {datetime.fromtimestamp(run['at']).strftime('%d/%m %H:%M')}   "
          f"{run['added']} nouveaux / {run['total']} au total")
    for source in run["sources"]:
        state = "ok  " if source["ok"] else "FAIL"
        print(f"  {state} {source['name']:<34} {source['count']:>4}  {source['detail']}")
    return 0


# ----------------------------------------------------------------------
def _write_html(path: str, store: Store, market_days: float) -> None:
    """The DEMO banner comes from the data, so it survives `hunter html` too."""
    leads = store.all()
    html = render_html(leads, market_table(leads, market_days), store.funnel())
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(html, encoding="utf-8")


def _telegram(leads: list) -> None:
    """Reuses the Telegram notifier already configured for this repo."""
    try:
        from forexai.notify import TelegramNotifier
    except ImportError:
        print("notifier indisponible (forexai.notify introuvable)")
        return
    notifier = TelegramNotifier.from_env()
    if not notifier.enabled:
        print("telegram non configuré (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID)")
        return
    notifier.send(format_telegram(leads))
    print(f"telegram : {len(leads)} lead(s) HOT envoyés")


COMMANDS = {"hunt": cmd_hunt, "list": cmd_list, "draft": cmd_draft, "mark": cmd_mark,
            "pipeline": cmd_pipeline, "market": cmd_market, "html": cmd_html,
            "sources": cmd_sources}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return COMMANDS[args.command](args)


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
