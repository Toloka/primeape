from __future__ import annotations

import argparse
import glob
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

from aggregate import balanced, summarize  # noqa: E402
from rationale_eval import SENT_SPLIT  # noqa: E402

EVAL = Path(__file__).resolve().parent / "results"
INPUT = EVAL / "rationales_input.parquet"
MASKED = EVAL / "masked"
NLI_EXCLUDED = {"yo"}

# verdict tokens and the word for "response" in each language
TOKEN = r"(?:A|B|Tie|[ÉE]galit[ée]|Empate|Uavgjort|बराबर|टाई|برابر|ٹائی|Dọ́gba|Ìdọ́gba)"
RESP = r"(?:Response|Answer|Réponse|Respuesta|Svar(?:et)?|उत्तर|جواب|Ìdáhùn|Idahun)"
# "<label of up to four words>: [Response] X" at the end of the text or of a line
LABELLED = re.compile(
    rf"(?:^|(?<=[\s.!?।۔]))[^\s.!?।۔:]+(?:\s+[^\s.!?।۔:]+){{0,3}}\s*[:：]\s*\**\s*(?:{RESP}\s+)?"
    rf"{TOKEN}\**\s*[.)]?\s*(?=$|\n)",
    re.I | re.M,
)
# a line or a trailing fragment that holds only verdict tokens ("B", "Tie/Tie/Tie", "(A)")
ONLY_TOKENS = re.compile(
    rf"^\W*(?:{RESP}\s+)?{TOKEN}(?:\s*[/,]\s*{TOKEN})*\W*$", re.I | re.M
)
TRAILING = re.compile(rf"(?<=[.!?।۔])\s+\(?(?:{RESP}\s+)?{TOKEN}\)?\.?\s*$", re.I)

# explicit preference or equality wording (m2)
PREFERENCE = {
    "en": r"\b(?:better|best|superior|inferior|worse|prefer(?:red|able|s)?|wins?|winner|outperforms?|"
    r"equal(?:ly)?|tied?|on par|comparable|indistinguishable|neither (?:is|response is) (?:better|preferable)|"
    r"no (?:clear|significant|meaningful|notable|real) (?:difference|winner|advantage))\b",
    "fr": r"\b(?:meilleure?s?|mieux|supérieure?s?|inférieure?s?|moins bonne?s?|préf[ée]r(?:able|ée?s?|e)|l'emporte|"
    r"égalité|équivalente?s?|comparables?|tout aussi|de manière égale|aucune différence)\b",
    "es": r"\b(?:mejor(?:es)?|superior(?:es)?|inferior(?:es)?|peor(?:es)?|preferible|preferid[ao]s?|empate|"
    r"igual(?:mente)?|equivalentes?|comparables?|por igual|ninguna diferencia)\b",
    "nb": r"\b(?:bedre|best|beste|dårligere|overlegen|foretrukk(?:et|ne)|foretrekkes|uavgjort|like (?:gode?|godt|"
    r"relevante?|naturlige?|sikre?|sanne?|korrekte?)|likeverdige?|likt|ingen (?:klar |vesentlig )?forskjell|"
    r"sammenlignbare|tilsvarende)\b",
    "hi": r"(?:बेहतर|श्रेष्ठ|सर्वश्रेष्ठ|पसंद|प्राथमिकता|बराबर|समान रूप से|एक समान|टाई|कोई अंतर नहीं|कोई फर्क नहीं)",
    "ur": r"(?:بہتر|بہترین|برتر|ترجیح|برابر|یکساں|مساوی|ٹائی|کوئی فرق نہیں)",
    "yo": r"(?:dára jù|dára ju|ju .{1,40}? lọ|dọ́gba|bákan náà|\btie\b)",
}
PREFERENCE = {k: re.compile(v, re.I) for k, v in PREFERENCE.items()}


def norm(text: str) -> str:
    return unicodedata.normalize("NFC", text or "")


def mask_tokens(text: str) -> str:
    t = LABELLED.sub(" ", norm(text))
    t = ONLY_TOKENS.sub(" ", t)
    t = TRAILING.sub("", t.strip())
    return " ".join(t.split())


def mask_sentences(text: str, lang: str) -> str:
    keep = [
        s
        for s in SENT_SPLIT.split(mask_tokens(text))
        if s.strip() and not PREFERENCE[lang].search(s)
    ]
    return " ".join(" ".join(keep).split())


def masked_frame(d: pd.DataFrame, level: str) -> pd.DataFrame:
    d = d.copy()
    d["original"] = d.rationale
    d["rationale"] = [
        mask_tokens(t) if level == "m1" else mask_sentences(t, l)
        for t, l in zip(d.rationale, d.lang)
    ]
    d["changed"] = d.rationale != d.original.map(lambda t: " ".join(norm(t).split()))
    d["rationale_status"] = np.where(
        d.rationale.str.split().str.len() >= 3, "ok", "masked_empty"
    )
    return d


def prepare(args) -> None:
    OUT = MASKED
    d = pd.read_parquet(INPUT)
    d = d[d.rationale_status == "ok"].reset_index(drop=True)
    OUT.mkdir(parents=True, exist_ok=True)
    stats = []
    for level in ["m1", "m2"]:
        m = masked_frame(d, level)
        m[["row_id", "rationale", "changed", "rationale_status"]].to_parquet(
            OUT / f"masked_{level}.parquet", index=False
        )
        run = m[m.changed & (m.rationale_status == "ok") & ~m.lang.isin(NLI_EXCLUDED)]
        run.drop(columns=["original", "changed"]).to_parquet(
            OUT / f"input_{level}.parquet", index=False
        )
        s = m.groupby(["lang", "setup"]).agg(
            n=("row_id", "size"),
            changed=("changed", "mean"),
            emptied=("rationale_status", lambda x: (x == "masked_empty").mean()),
        )
        stats.append(s.assign(level=level))
        print(
            f"{level}: {len(m):,} rationales, {m.changed.mean():.1%} changed, "
            f"{(m.rationale_status == 'masked_empty').mean():.1%} emptied, {len(run):,} to re-run"
        )
    pd.concat(stats).reset_index().to_csv(OUT / "masking_rates.csv", index=False)
    prepare_human(OUT)


def prepare_human(OUT: Path) -> None:
    """The human reference (verdict read from the human rationale) under the same m2 mask."""
    h = pd.read_parquet(INPUT)[
        ["lang", "crit", "instr", "pair", "human_label", "human_rationale"]
    ].drop_duplicates(["lang", "crit", "instr", "pair"])
    h = h[~h.lang.isin(NLI_EXCLUDED)].reset_index(drop=True)
    h = h.assign(
        row_id=np.arange(len(h)),
        rationale=h.human_rationale,
        setup="human",
        judge="human",
    )
    m = masked_frame(h, "m2")
    m.drop(columns=["original"]).to_parquet(
        OUT / "masked_human_m2.parquet", index=False
    )
    m[m.changed & (m.rationale_status == "ok")].drop(
        columns=["original", "changed"]
    ).to_parquet(OUT / "input_human_m2.parquet", index=False)
    print(
        f"human m2: {len(m):,} rationales, {m.changed.mean():.1%} changed, "
        f"{(m.rationale_status == 'masked_empty').mean():.1%} emptied"
    )


def human_reference(OUT: Path) -> dict:
    """class-balanced recovery of the human label from the human rationale, original and m2."""
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
    v = v[~v.lang.isin(NLI_EXCLUDED)]
    m = pd.read_parquet(OUT / "masked_human_m2.parquet")
    m = m.merge(
        v[["lang", "crit", "instr", "pair", "implied_verdict"]],
        on=["lang", "crit", "instr", "pair"],
    )
    new = nli_rows(OUT / "human_m2")[["row_id", "implied_verdict"]].rename(
        columns={"implied_verdict": "masked"}
    )
    m = m.merge(new, on="row_id", how="left")
    m["masked"] = np.where(m.changed, m.masked, m.implied_verdict)
    ok = m[m.rationale_status == "ok"]
    if ok.masked.isna().any():
        raise SystemExit(
            "human m2: masked rationales without an NLI verdict; run rationale_eval.py first"
        )
    return {
        "original": 100
        * balanced(v, "human_label", v.implied_verdict == v.human_label),
        "m2": 100 * balanced(ok, "human_label", ok.masked == ok.human_label),
    }


def nli_rows(path: Path) -> pd.DataFrame:
    files = sorted(
        glob.glob(str(path / "rows" / "nli_verdict_crosslingual" / "part-*.parquet"))
    )
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def analyze(args) -> None:
    OUT = MASKED
    orig = pd.read_parquet(EVAL / "crosslingual" / "rows_merged.parquet")
    orig = orig[orig.rationale_status == "ok"]
    ivc = "implied_verdict_crosslingual"

    variants = {"original": orig}
    for level in ["m1", "m2"]:
        m = pd.read_parquet(OUT / f"masked_{level}.parquet")
        new = nli_rows(OUT / level)[["row_id", "implied_verdict", "implied_max_entail"]]
        v = orig.drop(columns=["rationale_status"]).merge(
            m[["row_id", "changed", "rationale_status"]], on="row_id"
        )
        v = v.merge(new, on="row_id", how="left")
        missing = (
            v.changed
            & (v.rationale_status == "ok")
            & ~v.lang.isin(NLI_EXCLUDED)
            & v.implied_verdict.isna()
        )
        if missing.any():
            raise SystemExit(
                f"{level}: {missing.sum():,} masked rationales have no NLI verdict yet; "
                f"finish the rationale_eval.py run first"
            )
        # changed rows take the masked verdict; unchanged rows keep the original one
        v[ivc] = np.where(v.changed, v.implied_verdict, v[ivc])
        v["implied_max_entail_crosslingual"] = np.where(
            v.changed, v.implied_max_entail, v.implied_max_entail_crosslingual
        )
        variants[level] = v

    # as in the paper tables: per condition and judge, then the mean over judges and conditions
    keep_m2 = variants["m2"].loc[variants["m2"].rationale_status == "ok", "row_id"]
    rows = []
    for name, v in variants.items():
        for subset, r in [("all", v), ("m2_nonempty", v[v.row_id.isin(keep_m2)])]:
            r = r[r.rationale_status == "ok"]
            nli = r[~r.lang.isin(NLI_EXCLUDED)]
            for group, keys, rv in [
                ("all", [], r),
                ("verdict_correct", ["verdict_correct"], r[r.verdict_valid]),
            ]:
                s = summarize(
                    rv, ["setup"] + [k for k in keys if k != "setup"] + ["judge"]
                )
                s = (
                    s.groupby(keys)[["SC", "HA"]].mean().reset_index()
                    if keys
                    else s[["SC", "HA"]].mean().to_frame().T
                )
                for _, row in s.iterrows():
                    rows.append(
                        {
                            "text": name,
                            "subset": subset,
                            "group": group,
                            "level": "/".join(str(row[k]) for k in keys) or "all",
                            "SC": row.SC,
                            "HA": row.HA,
                            "decisive": 100
                            * (nli["implied_max_entail_crosslingual"] >= 0.5).mean(),
                        }
                    )
    res = pd.DataFrame(rows)
    res.to_csv(OUT / "masked_sc_hs.csv", index=False)
    pd.set_option("display.width", 200)
    print(
        res.pivot_table(
            index=["subset", "group", "level"],
            columns="text",
            values=["SC", "HA", "decisive"],
        )
        .round(1)
        .to_string()
    )

    by_judge = {
        n: summarize(v[v.rationale_status == "ok"], ["setup", "judge"])
        .groupby("judge")[["SC", "HA"]]
        .mean()
        for n, v in variants.items()
    }
    # the unmasked rationales of the examples that remain after the m2 mask (matched baseline for m2)
    retained = orig[orig.row_id.isin(keep_m2) & (orig.rationale_status == "ok")]
    by_judge["original_retained"] = (
        summarize(retained, ["setup", "judge"]).groupby("judge")[["SC", "HA"]].mean()
    )
    jt = pd.concat(by_judge, axis=1).round(1)
    jt.to_csv(OUT / "masked_by_judge.csv")
    print(jt.to_string())
    # each masked variant is compared with the unmasked rationales of the same examples
    spearman = lambda a, b: jt[(a, "SC")].corr(jt[(b, "SC")], method="spearman")
    print(
        "Spearman over judges, SC: original vs m1 %.2f; original (retained) vs m2 %.2f"
        % (spearman("original", "m1"), spearman("original_retained", "m2"))
    )
    rates = pd.read_csv(OUT / "masking_rates.csv")
    rates = rates[~rates.lang.isin(NLI_EXCLUDED)]
    tot = (
        rates.assign(c=rates.changed * rates.n, e=rates.emptied * rates.n)
        .groupby("level")[["n", "c", "e"]]
        .sum()
    )
    print("changed / emptied (share of rationales, NLI languages):")
    print((tot[["c", "e"]].div(tot.n, axis=0) * 100).round(1).to_string())
    ref = human_reference(OUT) if (OUT / "human_m2").exists() else {}
    print(
        "human reference (class-balanced, NLI languages):",
        {k: round(v, 1) for k, v in ref.items()},
    )


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("prepare")
    sub.add_parser("analyze")
    args = ap.parse_args()
    {"prepare": prepare, "analyze": analyze}[args.cmd](args)


if __name__ == "__main__":
    main()
