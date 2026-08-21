"""Command line interface.

    python -m forexai fetch --symbol EURUSD --timeframe 1h   # download real bars
    python -m forexai walkforward --bars 20000        # full validation + report
    python -m forexai backtest --source csv --path data/raw/EURUSD_H1.csv
    python -m forexai train                           # fit and save the model
    python -m forexai signal --llm                    # decision for the last closed bar
    python -m forexai paper --bars 500                # dry-run journal, no orders
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd

from . import __version__
from .config import Config
from .data.sources import load_market_data
from .metrics import (
    bootstrap_expectancy,
    compute_metrics,
    format_metrics,
    infer_bars_per_year,
)
from .pipeline import (
    build_dataset,
    explain_empty_dataset,
    fit_model,
    make_signals,
    run_backtest,
)
from .report import render, save, verdict
from .risk import RiskManager
from .signal import decide
from .walkforward import walk_forward

MODEL_PATH = Path("models/latest.joblib")


# ----------------------------------------------------------------------
# Shared options use argparse.SUPPRESS so a sub-command does not overwrite a
# value given before it. That means unset options are simply absent, so every
# read goes through a default rather than assuming the attribute exists.
OPTIONAL_ARGS = (
    "config", "symbol", "source", "path", "bars", "seed", "spread", "slippage",
    "commission", "frictionless", "risk", "equity",
    "train_bars", "test_bars", "step_bars",
)


def _load_config(args: argparse.Namespace) -> Config:
    opt = {name: getattr(args, name, None) for name in OPTIONAL_ARGS}

    cfg = Config.from_yaml(opt["config"]) if opt["config"] else Config()
    if opt["symbol"]:
        cfg.instrument.symbol = opt["symbol"]
    if opt["source"]:
        cfg.data.source = opt["source"]
    if opt["path"]:
        cfg.data.path = opt["path"]
        cfg.data.source = "csv"
    if opt["bars"]:
        cfg.data.bars = opt["bars"]
    if opt["seed"] is not None:
        cfg.data.seed = opt["seed"]
    if opt["spread"] is not None:
        cfg.costs.spread_pips = opt["spread"]
    if opt["slippage"] is not None:
        cfg.costs.slippage_pips = opt["slippage"]
    if opt["commission"] is not None:
        cfg.costs.commission_per_lot_roundturn = opt["commission"]
    if opt["frictionless"]:
        # Every friction, including the overnight swap that individual
        # overrides leave behind. Diagnostic only: it answers "is there a
        # signal here at all", never "is this tradable".
        cfg.costs.spread_pips = 0.0
        cfg.costs.slippage_pips = 0.0
        cfg.costs.commission_per_lot_roundturn = 0.0
        cfg.costs.swap_pips_per_night_long = 0.0
        cfg.costs.swap_pips_per_night_short = 0.0
        print(
            "FRICTIONLESS DIAGNOSTIC: spread, slippage, commission and swap are\n"
            "all zero. No broker on earth offers this. A result here answers one\n"
            "question only - whether the signal has any edge before costs. If it\n"
            "is positive here and negative with real costs, the signal is real\n"
            "but too small to pay the toll: look at a cheaper broker, a higher\n"
            "timeframe, or wider stops - not at the model."
        )
    if opt["risk"] is not None:
        cfg.risk.risk_per_trade = opt["risk"]
    if opt["equity"] is not None:
        cfg.initial_equity = opt["equity"]
    for name in ("train_bars", "test_bars", "step_bars"):
        if opt[name]:
            setattr(cfg.walk_forward, name, opt[name])
    return cfg


def _load_data(cfg: Config) -> pd.DataFrame:
    bars = load_market_data(cfg.data, cfg.instrument.symbol)
    print(
        f"data: {len(bars):,} bars  {bars.index[0]:%Y-%m-%d} -> {bars.index[-1]:%Y-%m-%d}  "
        f"source={cfg.data.source}"
    )
    if cfg.data.source == "synthetic":
        print(
            "      NOTE: synthetic data. It validates the machinery, it does not\n"
            "      validate an edge. Point --source csv at real bars before believing anything."
        )
    return bars


# ----------------------------------------------------------------------
def cmd_data(args: argparse.Namespace) -> int:
    cfg = _load_config(args)
    bars = _load_data(cfg)
    pip = cfg.instrument.pip_size
    rng = (bars["high"] - bars["low"]) / pip
    print(bars.tail(5).to_string())
    print(f"\nmedian bar range: {rng.median():.1f} pips   max: {rng.max():.1f} pips")
    gaps = bars.index.to_series().diff().value_counts().head(3)
    print(f"most common bar spacing:\n{gaps.to_string()}")
    return 0


def _describe_dataset(ds, cfg: Config) -> bool:
    """Report what the feed produced. Returns False when it is unusable."""
    trainable = ds.trainable()
    print(f"features: {len(ds.feature_names)}   labelled rows: {len(trainable):,}")
    if ds.dropped_features:
        print(
            f"          {len(ds.dropped_features)} feature(s) unavailable on this feed "
            f"and excluded: {', '.join(ds.dropped_features)}"
        )
    if len(trainable) >= cfg.model.min_train_samples:
        return True

    print(
        f"\nnot enough usable rows: {len(trainable):,} labelled, "
        f"{cfg.model.min_train_samples} needed.",
        file=sys.stderr,
    )
    print(explain_empty_dataset(ds), file=sys.stderr)
    print(
        "\nThe usual causes, in order of likelihood:\n"
        "  1. too little history - features need ~300 bars of warm-up and labels\n"
        f"     need {cfg.labels.max_holding_bars} bars of future to resolve\n"
        "  2. a column the feed cannot fill (listed above)\n"
        "  3. gaps or duplicated timestamps in the CSV\n"
        "Inspect the file with:  python -m forexai data --source csv --path <file>",
        file=sys.stderr,
    )
    return False


def cmd_fetch(args: argparse.Namespace) -> int:
    """Download real bars so nobody has to export anything by hand."""
    from .data.download import DownloadError, fetch, save_csv

    symbol = (args.symbol or "EURUSD").upper()
    timeframe = args.timeframe
    out = args.out or f"data/raw/{symbol}_{timeframe.upper()}.csv"

    print(f"downloading {symbol} {timeframe} (provider={args.provider}) ...")
    try:
        bars, provider = fetch(symbol, timeframe, args.years, args.provider)
    except DownloadError as exc:
        print(f"\ndownload failed:\n  {exc}", file=sys.stderr)
        return 1

    path = save_csv(bars, out)
    span_days = (bars.index[-1] - bars.index[0]).days
    print(
        f"\n{len(bars):,} bars from {provider}  "
        f"{bars.index[0]:%Y-%m-%d} -> {bars.index[-1]:%Y-%m-%d}  ({span_days} days)"
    )
    print(f"saved to {path}")

    if len(bars) < 5_000:
        print(
            f"\nWARNING: {len(bars):,} bars is thin. Walk-forward needs a training\n"
            "         window plus several forward windows; under ~5 000 bars you get\n"
            "         one or two folds and no statistical power. Use --timeframe 1d\n"
            "         for decades of history, or export H1 from your broker."
        )
    print(f"\nnext:\n  python -m forexai walkforward --source csv --path {path}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    """Test thousands of rule sets, then try to disqualify the winner."""
    from .search import format_search, grid_size, search_strategies

    cfg = _load_config(args)
    bars = _load_data(cfg)
    print(f"\nsearch space: {grid_size():,} combinations")

    result = search_strategies(
        bars, cfg,
        n_specs=args.n, top_k=args.top, holdout_fraction=args.holdout,
        min_trades=args.min_trades, seed=args.search_seed, jobs=args.jobs,
    )
    print()
    print(format_search(result))

    if not args.no_save:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        out = Path("runs") / f"search-{stamp}"
        out.mkdir(parents=True, exist_ok=True)
        table = result.table.drop(columns=["spec"], errors="ignore")
        table.to_csv(out / "all_candidates.csv", index=False)
        if not result.finalists.empty:
            result.finalists.drop(columns=["spec"], errors="ignore").to_csv(
                out / "finalists.csv", index=False
            )
        (out / "search.txt").write_text(format_search(result))
        cfg.dump(out / "config.yaml")
        print(f"\nartefacts written to {out}/")

    print(
        "\nRemember what this number is: the best of "
        f"{result.n_tested:,} tries. The deflated Sharpe above already accounts\n"
        "for that; the holdout columns are the real evidence. A strategy that wins\n"
        "the search and dies on the holdout is the search working, not failing."
    )
    return 0 if result.winner is not None else 2


def cmd_monitor(args: argparse.Namespace) -> int:
    """Watch the market bar by bar, on paper, and score itself as it goes."""
    import time

    from .monitor import Monitor
    from .notify import build_notifier, format_test

    blob = _load_model()
    if blob is None:
        return 1
    cfg = Config.from_dict(blob["config"])
    for attr in ("source", "path", "bars"):
        value = getattr(args, attr, None)
        if value:
            setattr(cfg.data, attr, value)
            if attr == "path":
                cfg.data.source = "csv"

    notifier = build_notifier(args.telegram)
    if args.test_alert:
        # A test of the Telegram path must not be satisfied by the console
        # fallback: printing to a log proves nothing about a phone.
        from .notify import TelegramNotifier

        telegram = TelegramNotifier.from_env()
        if not telegram.enabled:
            print(
                f"cannot test: {telegram.describe()}\n"
                "In GitHub Actions these come from repository secrets; "
                "locally, export them in your shell.",
                file=sys.stderr,
            )
            return 1
        message = format_test(cfg.instrument.symbol, cfg.data.timeframe)
        delivered, detail = telegram.deliver(message)
        if delivered:
            print("test alert delivered - check your phone")
            return 0
        print(f"test alert NOT delivered.\n\nTelegram said: {detail}", file=sys.stderr)
        return 1

    backtest_expectancy = _latest_bootstrap()
    monitor = Monitor(
        cfg, blob["model"], workdir=args.workdir,
        retrain_every=args.retrain_every,
        backtest_expectancy=backtest_expectancy,
        notifier=notifier,
    )
    if backtest_expectancy:
        print(
            f"drift reference: backtest expectancy "
            f"{backtest_expectancy.get('mean_r', 0):+.4f} R "
            f"(CI low {backtest_expectancy.get('ci_low', float('nan')):+.4f})"
        )
    else:
        print(
            "no walk-forward report found in runs/ - drift alerts are disabled.\n"
            "Run  python -m forexai walkforward  first to give the monitor a "
            "yardstick."
        )

    iterations = args.iterations if args.iterations > 0 else None
    count = 0
    while iterations is None or count < iterations:
        count += 1
        try:
            bars = load_market_data(cfg.data, cfg.instrument.symbol)
        except Exception as exc:                       # a feed hiccup is not fatal
            print(f"[{count}] data unavailable: {exc}")
            if args.interval <= 0:
                return 1
            time.sleep(args.interval)
            continue

        events = monitor.step(bars)
        stamp = datetime.now(timezone.utc).strftime("%H:%M:%S")
        if events:
            for event in events:
                detail = {k: v for k, v in event.items() if k not in ("ts", "kind")}
                print(f"[{stamp}] {event['kind']:<14} {detail}")
        else:
            print(f"[{stamp}] no new closed bar")

        if args.interval <= 0:
            break
        time.sleep(args.interval)

    print()
    print(monitor.summary())
    return 0


def _latest_bootstrap() -> dict:
    """Pull the expectancy confidence interval from the newest walk-forward run."""
    runs = sorted(Path("runs").glob("*/summary.json"))
    if not runs:
        return {}
    try:
        return json.loads(runs[-1].read_text()).get("bootstrap", {})
    except (OSError, json.JSONDecodeError):
        return {}


def cmd_walkforward(args: argparse.Namespace) -> int:
    cfg = _load_config(args)
    bars = _load_data(cfg)
    ds = build_dataset(bars, cfg)
    if not _describe_dataset(ds, cfg):
        return 1
    print("\nwalk-forward folds:")
    result = walk_forward(ds, cfg)
    if not result.folds:
        wf = cfg.walk_forward
        embargo = max(wf.embargo_bars, cfg.labels.max_holding_bars)
        needed = wf.train_bars + embargo + wf.test_bars
        have = len(ds.features)
        print(
            f"\nno fold could be built: one fold needs {needed:,} bars "
            f"(train {wf.train_bars:,} + embargo {embargo} + test {wf.test_bars:,}) "
            f"and this data has {have:,}.",
            file=sys.stderr,
        )
        if have > 2_000:
            train = int(have * 0.55)
            test = int(have * 0.15)
            print(
                "\nFor this much data, try:\n"
                f"  python -m forexai walkforward --source {cfg.data.source} "
                f"--path {cfg.data.path} \\\n"
                f"      --train-bars {train} --test-bars {test} --step-bars {test}",
                file=sys.stderr,
            )
        else:
            print("\nGet more history:  python -m forexai fetch --timeframe 1d "
                  "--provider stooq", file=sys.stderr)
        return 1
    print()
    print(render(result, cfg, title=f"FOREX AI v{__version__}"))
    if not args.no_save:
        path = save(result, cfg)
        print(f"\nartefacts written to {path}/")
    label, _ = verdict(result)
    return 0 if label != "NO-GO" else 2


def cmd_backtest(args: argparse.Namespace) -> int:
    cfg = _load_config(args)
    bars = _load_data(cfg)
    ds = build_dataset(bars, cfg)
    if not _describe_dataset(ds, cfg):
        return 1

    index = ds.features.index
    split = int(len(index) * (1.0 - args.test_fraction))
    embargo = max(cfg.walk_forward.embargo_bars, cfg.labels.max_holding_bars)
    train_idx, test_idx = index[:split], index[split + embargo :]
    print(
        f"train {train_idx[0]:%Y-%m-%d} -> {train_idx[-1]:%Y-%m-%d} ({len(train_idx):,} bars) | "
        f"embargo {embargo} bars | "
        f"test {test_idx[0]:%Y-%m-%d} -> {test_idx[-1]:%Y-%m-%d} ({len(test_idx):,} bars)"
    )

    model = fit_model(ds, train_idx, cfg)
    signals = make_signals(model, ds, test_idx, cfg)
    result = run_backtest(ds, signals, test_idx, cfg)
    metrics = compute_metrics(
        result.trades, result.equity, cfg.initial_equity,
        bars_per_year=infer_bars_per_year(test_idx),
    )

    print("\nout-of-sample result:")
    print(format_metrics(metrics))
    print(f"\nbootstrap: {bootstrap_expectancy(result.trades)}")
    if result.rejections:
        print("\nrisk-manager vetoes:")
        for reason, count in sorted(result.rejections.items(), key=lambda kv: -kv[1]):
            print(f"  {count:>6}  {reason}")
    if result.halted:
        print(f"\n!! {result.halt_reason}")
    return 0


def cmd_train(args: argparse.Namespace) -> int:
    cfg = _load_config(args)
    bars = _load_data(cfg)
    ds = build_dataset(bars, cfg)
    if not _describe_dataset(ds, cfg):
        return 1
    train_idx = ds.trainable()
    model = fit_model(ds, train_idx, cfg)

    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(
        {
            "model": model,
            "config": cfg.to_dict(),
            "trained_at": datetime.now(timezone.utc).isoformat(),
            "train_rows": len(train_idx),
            "data_end": str(bars.index[-1]),
            "version": __version__,
        },
        MODEL_PATH,
    )
    print(f"\ntrained on {len(train_idx):,} rows -> {MODEL_PATH}")
    print(f"class balance: {model.report.class_counts}")
    print("\ntop features:")
    print(model.feature_importance(12).round(4).to_string())
    print(
        "\nWARNING: a model fitted on all history has no honest test set left.\n"
        "         Use it to trade forward, never to justify a backtest number."
    )
    return 0


def _load_model():
    if not MODEL_PATH.exists():
        print(f"no saved model at {MODEL_PATH} - run:  python -m forexai train", file=sys.stderr)
        return None
    return joblib.load(MODEL_PATH)


def cmd_signal(args: argparse.Namespace) -> int:
    blob = _load_model()
    if blob is None:
        return 1
    cfg = Config.from_dict(blob["config"])
    if args.bars:
        cfg.data.bars = args.bars
    if args.source:
        cfg.data.source = args.source
    if args.path:
        cfg.data.source, cfg.data.path = "csv", args.path

    bars = _load_data(cfg)
    ds = build_dataset(bars, cfg)
    idx = ds.predictable()
    if len(idx) == 0:
        print("not enough history to compute features", file=sys.stderr)
        return 1

    last = idx[-1]
    recent = idx[-min(len(idx), args.history):]
    signals = make_signals(blob["model"], ds, recent, cfg)
    decision = decide(signals.loc[last])

    print(f"\nlast closed bar : {last}  close {ds.bars.loc[last, 'close']:.5f}")
    print(f"model trained   : {blob['trained_at']}  ({blob['train_rows']:,} rows)")
    print(f"decision        : {decision}")

    if args.llm:
        from .llm import apply_review, build_context, review as llm_review

        ctx = build_context(
            ds.features.loc[last], decision, ds.bars.loc[last, "close"], cfg.instrument.pip_size
        )
        rev = llm_review(ctx, model=args.llm_model)
        direction, note = apply_review(decision.direction, rev)
        print(f"llm review      : {'online' if rev.available else 'offline'} - {note}")
        decision.direction = direction

    rm = RiskManager(cfg.risk, cfg.instrument, cfg.costs, cfg.initial_equity)
    rm.on_new_bar(last)
    plan = rm.evaluate(
        timestamp=last,
        direction=decision.direction,
        reference_price=float(ds.bars.loc[last, "close"]),
        atr=float(ds.features.loc[last, "atr"]),
    )
    print(f"risk manager    : {plan}")

    # The alert is the deliverable: the exact order, or an explicit "do nothing".
    from .notify import build_notifier, format_trade_alert

    alert = format_trade_alert(
        symbol=cfg.instrument.symbol,
        timeframe=cfg.data.timeframe,
        bar_time=last,
        decision=decision,
        plan=plan,
        equity=cfg.initial_equity,
    )
    print("\n" + "-" * 62)
    print(alert)
    print("-" * 62)

    if args.telegram:
        notifier = build_notifier(True)
        if notifier is not None and getattr(notifier, "enabled", False):
            print("alert sent" if notifier.send(alert) else "alert could not be delivered")

    # A quiet market is the normal case, and a bare "WAIT" looks like a broken
    # program. Show when the system last actually wanted to trade.
    if decision.direction == 0:
        acted = signals.index[signals["direction"] != 0]
        taken = (signals["direction"] != 0).sum()
        print(
            f"\nover the last {len(recent):,} bars the system proposed "
            f"{taken} trade(s) ({100.0 * taken / max(len(recent), 1):.1f}% of bars)."
        )
        if len(acted):
            when = acted[-1]
            past = decide(signals.loc[when])
            past_rm = RiskManager(cfg.risk, cfg.instrument, cfg.costs, cfg.initial_equity)
            past_rm.on_new_bar(when)
            past_plan = past_rm.evaluate(
                timestamp=when,
                direction=past.direction,
                reference_price=float(ds.bars.loc[when, "close"]),
                atr=float(ds.features.loc[when, "atr"]),
            )
            print(f"\nmost recent actionable signal was {when} (historical, do not trade it):")
            print("-" * 62)
            print(
                format_trade_alert(
                    symbol=cfg.instrument.symbol, timeframe=cfg.data.timeframe,
                    bar_time=when, decision=past, plan=past_plan,
                    equity=cfg.initial_equity,
                )
            )
            print("-" * 62)
        else:
            print("It has not wanted to trade once in that window.")

    print(
        "\n(The reference price is the last close; a live order fills at the next\n"
        " open, so re-run at the bar boundary before acting.)"
    )
    return 0


def cmd_paper(args: argparse.Namespace) -> int:
    """Replay the most recent bars one at a time and journal every decision."""
    blob = _load_model()
    if blob is None:
        return 1
    cfg = Config.from_dict(blob["config"])
    if args.source:
        cfg.data.source = args.source
    if args.path:
        cfg.data.source, cfg.data.path = "csv", args.path

    bars = _load_data(cfg)
    ds = build_dataset(bars, cfg)
    idx = ds.predictable()[-args.replay_bars :]
    signals = make_signals(blob["model"], ds, idx, cfg)
    result = run_backtest(ds, signals, idx, cfg)

    print(f"\npaper replay over {len(idx):,} bars (no orders sent)")
    trained_until = pd.Timestamp(blob.get("data_end", "1970-01-01"))
    if idx[0] <= trained_until:
        overlap = int((idx <= trained_until).sum())
        print(
            f"WARNING: {overlap:,} of these bars were in the training set. "
            "This replay is in-sample\n"
            "         and flatters the model - read it as a smoke test, not as a result.\n"
            "         For an honest number use:  python -m forexai walkforward"
        )
    if result.trades.empty:
        print("no trade passed the risk gate in this window.")
    else:
        cols = ["entry_time", "direction", "lots", "entry", "exit",
                "exit_reason", "pnl", "r_multiple", "equity_after"]
        print(result.trades[cols].to_string(index=False))
        print()
        print(
            format_metrics(
                compute_metrics(
                    result.trades, result.equity, cfg.initial_equity,
                    bars_per_year=infer_bars_per_year(idx),
                )
            )
        )
    if result.rejections:
        print("\nvetoes:")
        for reason, count in sorted(result.rejections.items(), key=lambda kv: -kv[1]):
            print(f"  {count:>6}  {reason}")
    return 0


# ----------------------------------------------------------------------
def _global_options() -> argparse.ArgumentParser:
    """Shared options, accepted either before or after the sub-command."""
    common = argparse.ArgumentParser(add_help=False, argument_default=argparse.SUPPRESS)
    common.add_argument("--config", help="path to a YAML config file")
    common.add_argument("--symbol", help="instrument symbol, e.g. EURUSD")
    common.add_argument("--source", choices=["synthetic", "csv", "yahoo"])
    common.add_argument("--path", help="CSV file with OHLCV bars")
    common.add_argument("--bars", type=int, help="how many bars to use")
    common.add_argument("--seed", type=int, help="synthetic data seed")
    common.add_argument("--spread", type=float, help="override spread in pips")
    common.add_argument("--slippage", type=float, help="override slippage in pips per side")
    common.add_argument("--commission", type=float,
                        help="override commission per lot round turn")
    common.add_argument("--frictionless", action="store_true",
                        help="zero every cost including swap - a diagnostic that "
                             "answers whether the signal has any edge before costs")
    common.add_argument("--risk", type=float, help="risk per trade, e.g. 0.005")
    common.add_argument("--equity", type=float, help="starting equity")
    return common


def build_parser() -> argparse.ArgumentParser:
    common = _global_options()
    parser = argparse.ArgumentParser(
        prog="forexai",
        description=f"FOREX AI v{__version__} - hybrid trading research stack",
        parents=[common],
    )

    sub = parser.add_subparsers(dest="command", required=True)
    dt = sub.add_parser("data", help="load and describe the market data", parents=[common])
    dt.set_defaults(func=cmd_data)

    fe = sub.add_parser("fetch", help="download real bars to a CSV", parents=[common])
    fe.add_argument("--timeframe", default="1h", choices=["1h", "1d", "30m", "15m", "5m"])
    fe.add_argument("--years", type=float, default=2.0, help="how much history to ask for")
    fe.add_argument("--provider", default="auto", choices=["auto", "yahoo", "stooq"])
    fe.add_argument("--out", help="destination CSV (default data/raw/<SYMBOL>_<TF>.csv)")
    fe.set_defaults(func=cmd_fetch)

    wf = sub.add_parser(
        "walkforward", aliases=["wf"], help="rolling out-of-sample validation", parents=[common]
    )
    wf.add_argument("--no-save", action="store_true", help="do not write artefacts to runs/")
    wf.add_argument("--train-bars", type=int, help="bars per training window")
    wf.add_argument("--test-bars", type=int, help="bars traded forward per fold")
    wf.add_argument("--step-bars", type=int, help="bars between folds")
    wf.set_defaults(func=cmd_walkforward)

    bt = sub.add_parser("backtest", help="single train/test split backtest", parents=[common])
    bt.add_argument("--test-fraction", type=float, default=0.3)
    bt.set_defaults(func=cmd_backtest)

    tr = sub.add_parser("train", help="fit on all data and save the model", parents=[common])
    tr.set_defaults(func=cmd_train)

    sg = sub.add_parser("signal", help="decision for the last closed bar", parents=[common])
    sg.add_argument("--llm", action="store_true", help="ask the local LLM for a risk review")
    sg.add_argument("--llm-model", default="llama3.2:3b")
    sg.add_argument("--telegram", action="store_true",
                    help="also send the alert to Telegram")
    sg.add_argument("--history", type=int, default=500,
                    help="bars of context used to show recent signal activity")
    sg.set_defaults(func=cmd_signal)

    se = sub.add_parser(
        "search", help="test thousands of rule strategies against a holdout", parents=[common]
    )
    se.add_argument("--n", type=int, default=2_000, help="candidates to sample")
    se.add_argument("--top", type=int, default=10, help="finalists taken to the holdout")
    se.add_argument("--holdout", type=float, default=0.35, help="fraction held back")
    se.add_argument("--min-trades", type=int, default=30)
    se.add_argument("--search-seed", type=int, default=0)
    se.add_argument("--jobs", type=int, default=1, help="parallel workers")
    se.add_argument("--no-save", action="store_true")
    se.set_defaults(func=cmd_search)

    mo = sub.add_parser(
        "monitor", help="watch the market on paper and score the model live", parents=[common]
    )
    mo.add_argument("--interval", type=float, default=0.0,
                    help="seconds between checks; 0 runs a single pass (use with cron)")
    mo.add_argument("--iterations", type=int, default=0, help="0 = run until stopped")
    mo.add_argument("--retrain-every", type=int, default=500,
                    help="bars between refits; 0 disables retraining")
    mo.add_argument("--workdir", default="runs/monitor")
    mo.add_argument("--telegram", action="store_true",
                    help="send actionable alerts to Telegram "
                         "(needs TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)")
    mo.add_argument("--test-alert", action="store_true",
                    help="send one test message and exit, touching no state")
    mo.set_defaults(func=cmd_monitor)

    pp = sub.add_parser("paper", help="dry-run replay of recent bars", parents=[common])
    pp.add_argument("--window", type=int, default=500, dest="replay_bars",
                    help="how many recent bars to replay")
    pp.set_defaults(func=cmd_paper)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    for attr in OPTIONAL_ARGS:
        if not hasattr(args, attr):
            setattr(args, attr, None)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
