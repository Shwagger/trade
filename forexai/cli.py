"""Command line interface.

    python -m forexai walkforward --bars 20000        # full validation + report
    python -m forexai backtest --source csv --path data/raw/EURUSD_H1.csv
    python -m forexai train                           # fit and save the model
    python -m forexai signal --llm                    # decision for the last closed bar
    python -m forexai paper --bars 500                # dry-run journal, no orders
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import pandas as pd

from . import __version__
from .config import Config
from .data.sources import load_market_data
from .metrics import bootstrap_expectancy, compute_metrics, format_metrics
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
    metrics = compute_metrics(result.trades, result.equity, cfg.initial_equity)

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
        print(format_metrics(compute_metrics(result.trades, result.equity, cfg.initial_equity)))
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
