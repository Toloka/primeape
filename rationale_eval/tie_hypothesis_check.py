from __future__ import annotations

import argparse
import glob
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rationale_eval import MODELS, NLI  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "rationale_eval" / "results"
OUT = EVAL / "tie_hypothesis"
NLI_EXCLUDED = {"yo"}
TIE_HYPOTHESES = {
    "good": "Response A and Response B are equally good.",
    "bad": "Response A and Response B are equally bad.",
    "good_or_bad": "Response A and Response B are equally good or equally bad.",
}
VARIANTS = {
    "good": ["good"],
    "good_or_bad": ["good_or_bad"],
    "max_good_bad": ["good", "bad"],
}


def load_rationales() -> pd.DataFrame:
    files = sorted(
        glob.glob(
            str(
                EVAL
                / "crosslingual"
                / "rows"
                / "nli_validation_crosslingual"
                / "part-*.parquet"
            )
        )
    )
    v = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    h = pd.read_parquet(EVAL / "rationales_input.parquet")[
        ["lang", "crit", "instr", "pair", "human_rationale"]
    ].drop_duplicates(["lang", "crit", "instr", "pair"])
    return v.merge(
        h, on=["lang", "crit", "instr", "pair"], how="left", validate="one_to_one"
    )


def entailment(v: pd.DataFrame, batch_size: int) -> pd.DataFrame:
    path = OUT / "entailment.parquet"
    if path.exists():
        return pd.read_parquet(path)
    nli = NLI(MODELS["nli"], batch_size)
    texts = list(v.human_rationale)
    res = v[["lang", "crit", "instr", "pair"]].copy()
    for name, hyp in TIE_HYPOTHESES.items():
        res[f"p_{name}"] = nli(texts, [hyp] * len(texts))[:, 0]
        print(f"  scored '{name}'", flush=True)
    OUT.mkdir(parents=True, exist_ok=True)
    res.to_parquet(path, index=False)
    return res


def evaluate(d: pd.DataFrame, variant: str) -> dict:
    """Class-balanced recall of the human label when Tie uses the variant's hypotheses."""
    tie = d[[f"p_{h}" for h in VARIANTS[variant]]].max(axis=1).to_numpy()
    probs = np.column_stack([d.p_entail_A, d.p_entail_B, tie])
    pred = np.array(["A", "B", "tie"])[probs.argmax(axis=1)]
    y = d.human_label.to_numpy()
    recall = {c: float((pred[y == c] == c).mean()) * 100 for c in ["A", "B", "tie"]}
    return {
        "variant": variant,
        "balanced_recall": np.mean(list(recall.values())),
        **{f"recall_{c}": r for c, r in recall.items()},
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--batch-size", type=int, default=8)
    args = ap.parse_args()
    v = load_rationales()
    d = v.merge(
        entailment(v, args.batch_size),
        on=["lang", "crit", "instr", "pair"],
        validate="one_to_one",
    )
    # sanity check: the re-scored "equally good" reproduces the stored Tie entailment
    diff = (d.p_good - d.p_entail_tie).abs()
    print(
        f"re-scored 'equally good' vs stored: max |dp| = {diff.max():.3f}, "
        f"{(diff < 0.03).mean():.1%} within 0.03"
    )

    six = d[~d.lang.isin(NLI_EXCLUDED)]
    summary = pd.DataFrame([evaluate(six, k) for k in VARIANTS])
    summary.to_csv(OUT / "summary.csv", index=False)
    print(f"\nsix NLI languages (n = {len(six):,}):")
    print(summary.round(1).to_string(index=False))


if __name__ == "__main__":
    main()
