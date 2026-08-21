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
from .pipeline import build_dataset, fit_model, make_signals, run_backtest
from .report import render, save, verdict
from .risk import RiskManager
from .signal import decide
from .walkforward import walk_forward

MODEL_PATH = Path("models/latest.joblib")


# ----------------------------------------------------------------------
def _load_config(args: argparse.Namespace) -> Config:
    cfg = Config.from_yaml(args.config) if args.config else Config()
    if args.symbol:
        cfg.instrument.symbol = args.symbol
    if args.source:
        cfg.data.source = args.source
    if args.path:
        cfg.data.path = args.path
        cfg.data.source = "csv"
    if args.bars:
        cfg.data.bars = args.bars
    if args.seed is not None:
        cfg.data.seed = args.seed
    if args.spread is not None:
        cfg.costs.spread_pips = args.spread
    if args.risk is not None:
        cfg.risk.risk_per_trade = args.risk
    if args.equity is not None:
        cfg.initial_equity = args.equity
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
    from .notify import build_notifier

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

    backtest_expectancy = _latest_bootstrap()
    monitor = Monitor(
        cfg, blob["model"], workdir=args.workdir,
        retrain_every=args.retrain_every,
        backtest_expectancy=backtest_expectancy,
        notifier=build_notifier(args.telegram),
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
    print(f"features: {len(ds.feature_names)}   labelled rows: {len(ds.trainable()):,}")
    print("\nwalk-forward folds:")
    result = walk_forward(ds, cfg)
    if not result.folds:
        print(
            "no fold could be built - reduce walk_forward.train_bars/test_bars "
            "or supply more data."
        )
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
    signals = make_signals(blob["model"], ds, pd.Index([last]), cfg)
    decision = decide(signals.iloc[-1])

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
    wf.set_defaults(func=cmd_walkforward)

    bt = sub.add_parser("backtest", help="single train/test split backtest", parents=[common])
    bt.add_argument("--test-fraction", type=float, default=0.3)
    bt.set_defaults(func=cmd_backtest)

    tr = sub.add_parser("train", help="fit on all data and save the model", parents=[common])
    tr.set_defaults(func=cmd_train)

    sg = sub.add_parser("signal", help="decision for the last closed bar", parents=[common])
    sg.add_argument("--llm", action="store_true", help="ask the local LLM for a risk review")
    sg.add_argument("--llm-model", default="llama3.2:3b")
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
    mo.set_defaults(func=cmd_monitor)

    pp = sub.add_parser("paper", help="dry-run replay of recent bars", parents=[common])
    pp.add_argument("--window", type=int, default=500, dest="replay_bars",
                    help="how many recent bars to replay")
    pp.set_defaults(func=cmd_paper)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    for attr in ("config", "symbol", "source", "path", "bars", "seed", "spread", "risk", "equity"):
        if not hasattr(args, attr):
            setattr(args, attr, None)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
