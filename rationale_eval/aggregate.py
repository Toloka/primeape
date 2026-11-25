from __future__ import annotations

import argparse
import glob
from pathlib import Path

import numpy as np
import pandas as pd

EVAL = Path(__file__).resolve().parent / "results"
M = "_crosslingual"
LANGS = ["en", "fr", "hi", "nb", "es", "ur", "yo"]
NLI_EXCLUDED = {"yo"}
VERDICTS = ["A", "B", "tie"]
COLS = ["Expl", "Words", "chrF", "Cos", "SC", "HA", "Sup", "Con", "Cov"]


def load(results: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    r = pd.read_parquet(results / "rows_merged.parquet")
    files = sorted(
        glob.glob(str(results / "rows" / f"nli_validation{M}" / "part-*.parquet"))
    )
    v = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    return r, v


def balanced(d: pd.DataFrame, by: str, hit: pd.Series) -> float:
    """mean over classes of `by` of the hit rate (class-balanced recall)."""
    rates = hit.groupby(d[by]).mean()
    return float(rates.reindex(VERDICTS).dropna().mean()) if len(rates) else np.nan


def summarize(
    r: pd.DataFrame, keys: list[str], nli_excluded: set = NLI_EXCLUDED
) -> pd.DataFrame:
    """One row per group in `keys`: presence and words (all rows), mean metrics and
    class-balanced NLI metrics (rationales present, NLI languages only)."""
    rows = []
    for k, g in r.groupby(keys) if keys else [((), r)]:
        k = k if isinstance(k, tuple) else (k,)
        ok = g[g.rationale_status == "ok"]
        nli = ok[~ok.lang.isin(nli_excluded)]
        valid = nli[nli.judge_verdict.notna()]
        row = dict(zip(keys, k))
        row["Expl"] = 100 * (g.rationale_status == "ok").mean()
        row["Words"] = ok.rationale_words.mean()
        row["chrF"] = 100 * ok.chrf.mean()
        row["Cos"] = 100 * ok.embed_cosine.mean()
        row["SC"] = 100 * balanced(
            valid, "judge_verdict", valid[f"implied_verdict{M}"] == valid.judge_verdict
        )
        row["HA"] = 100 * balanced(
            nli, "human_label", nli[f"implied_verdict{M}"] == nli.human_label
        )
        row["Sup"] = 100 * nli[f"nli_support{M}"].mean()
        row["Con"] = 100 * nli[f"nli_contra{M}"].mean()
        row["Cov"] = 100 * nli[f"nli_coverage{M}"].mean()
        row["n_ok"] = len(ok)
        rows.append(row)
    return pd.DataFrame(rows)


def human_reference(v: pd.DataFrame) -> float:
    six = v[~v.lang.isin(NLI_EXCLUDED)]
    return 100 * balanced(six, "human_label", six.implied_verdict == six.human_label)


def by_language(r: pd.DataFrame, v: pd.DataFrame) -> pd.DataFrame:
    per = summarize(r, ["setup", "lang", "judge"]).groupby("lang")[COLS].mean()
    # Yoruba NLI values are shown for completeness, computed without the exclusion
    per.loc["yo"] = (
        summarize(r[r.lang == "yo"], ["setup", "judge"], set())
        .groupby("judge")[COLS]
        .mean()
        .mean()
    )
    per["Ref"] = pd.Series(
        {
            l: 100 * balanced(g, "human_label", g.implied_verdict == g.human_label)
            for l, g in v.groupby("lang")
        }
    )
    return per.reindex(LANGS)


def nli_validation(v: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for lang in LANGS:
        g = v[v.lang == lang]
        hit = g.implied_verdict == g.human_label
        rec = hit.groupby(g.human_label).mean().reindex(VERDICTS) * 100
        f1 = [
            2
            * ((g.human_label == c) & (g.implied_verdict == c)).sum()
            / ((g.human_label == c).sum() + (g.implied_verdict == c).sum())
            for c in VERDICTS
            if (g.human_label == c).any()
        ]
        rows.append(
            {
                "lang": lang,
                "n": len(g),
                "acc": 100 * hit.mean(),
                "macro_f1": 100 * np.mean(f1),
                "rec_A": rec["A"],
                "rec_B": rec["B"],
                "rec_tie": rec["tie"],
                "decisive": 100 * (g.implied_max_entail >= 0.5).mean(),
            }
        )
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--results", type=Path, default=EVAL / "crosslingual")
    ap.add_argument("--out", type=Path, default=EVAL / "aggregates")
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    r, v = load(args.results)
    per = summarize(r, ["setup", "judge"])
    tables = {
        "by_judge": per.groupby("judge")[COLS]
        .mean()
        .sort_values("SC", ascending=False),
        "by_condition_judge": per.set_index(["setup", "judge"]),
        "by_language": by_language(r, v),
        "by_correctness": summarize(
            r[r.verdict_valid], ["setup", "verdict_correct", "judge"]
        )
        .groupby(["setup", "verdict_correct"])[COLS]
        .mean(),
        "nli_validation_by_language": nli_validation(v).set_index("lang"),
    }
    for name, t in tables.items():
        t.to_csv(args.out / f"{name}.csv")
    with pd.option_context("display.width", 200):
        print(tables["by_judge"].round(1).to_string())
        print(
            "\nhuman reference (class-balanced, 6 languages):",
            round(human_reference(v), 1),
        )
        print(tables["by_language"].round(1).to_string())
    print(f"wrote CSVs -> {args.out}/")


if __name__ == "__main__":
    main()
