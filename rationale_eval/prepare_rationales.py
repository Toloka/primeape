from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "parsers"))
from judge_parser import (
    ALIASES,
    CRITERIA,
    MAX_RESPONSE_LEN,
    SINGLE_LABELS_FOLDED,  # noqa: E402
    clean,
    fold,
    label_key,
    value,
)

SETUPS = ["joint_r", "criterion_r"]
LANGS = ["en", "fr", "hi", "nb", "es", "ur", "yo"]
JUDGE_NAMES = {
    "anthropic/claude-sonnet-4": "Claude-Sonnet-4",
    "deepseek/deepseek-chat-v3-0324": "DeepSeek-V3",
    "google/gemini-2.5-pro": "Gemini-2.5-Pro",
    "meta-llama/llama-3.1-70b-instruct": "LLaMA-3.1-70B",
    "meta-llama/llama-3.1-8b-instruct": "LLaMA-3.1-8B",
    "meta-llama/llama-3.3-70b-instruct": "LLaMA-3.3-70B",
    "microsoft/phi-4-mini-instruct": "Phi-4-mini",
    "openai/gpt-4o-mini": "GPT-4o-mini",
    "openai/gpt-5": "GPT-5",
    "qwen/qwen-2.5-72b-instruct": "Qwen2.5-72B",
    "qwen/qwen-2.5-7b-instruct": "Qwen2.5-7B",
    "qwen/qwen3-32b": "Qwen3-32B",
}
VERDICT_PREFIX = re.compile(
    r"^\W*(?:(?:response|answer|option|réponse|respuesta|svar|ìdáhùn|उत्तर|جواب)\s+)?(?:A|B|Tie)\b[\s:—–\-(),.]*",
    re.I,
)
SEPARATOR = re.compile(r"^\s*(?:#+\s|-{3,}|\*{3,}|_{3,}|={3,})")
_ALIASES_BY_LENGTH = sorted(ALIASES, key=len, reverse=True)


def crit_of(key: str) -> str | None:
    """Criterion named by a label: exact name, or a short label starting with one
    ("relevance analysis", "مطابقت کا تجزیہ", "truthfulness (accuracy)")."""
    if key in ALIASES:
        return ALIASES[key]
    if len(key.split()) <= 6:
        for alias in _ALIASES_BY_LENGTH:
            if key.startswith(alias + " ") or key.startswith(alias + "("):
                return ALIASES[alias]
    return None


def opening_crit(raw: str) -> str | None:
    """Criterion named in the first words of a prose paragraph
    ("For Relevance, ...", "In terms of Naturalness, ...", "Overall, ...")."""
    head = " " + label_key(" ".join(raw.split()[:6])).replace(",", " ") + " "
    for alias in _ALIASES_BY_LENGTH:
        pos = head.find(" " + alias + " ")
        if 0 <= pos and len(head[:pos].split()) <= 3:
            return ALIASES[alias]
    return None


def classify(line: str, criterion: str | None = None):
    """-> (kind, crit, text); kind in blank | label | verdict | heading | separator | other.

    label   : criterion name followed by explanatory text (> 4 words)
    verdict : criterion name (or answer word) followed by a verdict / short value;
              text holds any inline rationale after the verdict
    """
    raw = clean(line).strip(" -•*>")
    if not raw:
        return "blank", None, ""
    if SEPARATOR.match(line.strip()):
        heading = crit_of(label_key(re.sub(r"^#+\s*", "", raw).rstrip(":")))
        return ("heading", heading, "") if heading else ("separator", None, "")
    parts = re.split("[:：]", raw, maxsplit=1)
    if len(parts) == 2:
        key = label_key(parts[0])
        c = crit_of(key)
        if c is None and fold(key) in SINGLE_LABELS_FOLDED:
            c = criterion or "_answer"
        if c is not None:
            rest = parts[1].strip()
            if not rest and c != "_answer":
                return (
                    "heading",
                    c,
                    "",
                )  # "1. **Relevance:**" followed by its explanation
            if value(rest) is not None:
                return "verdict", c, VERDICT_PREFIX.sub("", rest).strip()
            if len(rest.split()) <= 4:
                return "verdict", c, ""
            return "label", c, rest
        if len(raw.split()) <= 5 and raw.endswith(":"):
            return "separator", None, ""  # e.g. "**Final verdicts:**"
    heading = crit_of(label_key(raw.rstrip(":")))
    if heading is not None:
        return "heading", heading, ""
    if value(raw, False) is not None:
        return "verdict", criterion or "_answer", ""
    return "other", None, raw


def _join(chunks: list[str]) -> str:
    return " ".join(" ".join(c.split()) for c in chunks if c.strip()).strip()


def segment_combined(text: str) -> dict[str, str]:
    blocks = {c: [] for c in CRITERIA}
    current, pending, prev_blank = None, [], True
    for line in text.splitlines():
        kind, c, rest = classify(line)
        if (
            kind == "other"
            and prev_blank
            and len(rest.split()) > 8
            and (o := opening_crit(rest))
        ):
            kind, c = "label", o  # a prose paragraph introducing a criterion
        prev_blank = kind == "blank"
        if kind == "label" and c not in blocks:
            kind = (
                "other"  # "Answer: Response A is ..." inside a section: ordinary text
            )
        if kind == "label":
            current, pending = c, []
            blocks[c].append(rest)
        elif kind == "heading":
            current, pending = c, []
        elif kind == "verdict":
            if c in blocks:
                if rest:
                    blocks[c].append(rest)
                if not _join(blocks[c]) and pending:
                    blocks[c].extend(pending)  # "For relevance, ... \n - Relevance: A"
            current, pending = None, []
        elif kind == "separator":
            current, pending = None, []
        elif kind == "other":
            if current is not None:
                blocks[current].append(rest)
            else:
                pending.append(rest)
        # blank lines keep the current block open
    return {c: _join(v) for c, v in blocks.items()}


def segment_separated(text: str, criterion: str) -> str:
    keep = []
    for line in text.splitlines():
        kind, c, rest = classify(line, criterion)
        if kind in ("other", "label"):
            keep.append(rest)
        elif kind == "verdict" and rest:
            keep.append(rest)
    return _join(keep)


def status(text: str | None, rationale: str) -> str:
    if text is None or not str(text).strip():
        return "no_response"
    if len(text) > MAX_RESPONSE_LEN:
        return "over_length"
    return "ok" if len(rationale.split()) >= 3 else "empty"


def human_table(dataset: str) -> dict:
    from datasets import load_dataset

    out = {}
    for lang in LANGS:
        df = load_dataset(dataset, lang, split="test").to_pandas()
        for r in df.itertuples():
            out[(lang, r.id, frozenset([r.generator_a, r.generator_b]))] = r
    return out


def records(source: Path, setup: str):
    if source.is_file():
        with open(source, encoding="utf-8") as f:
            for r in map(json.loads, f):
                if r["condition"] == setup:
                    yield r
        return
    for lang in LANGS:
        with open(source / setup / f"{lang}.jsonl", encoding="utf-8") as f:
            yield from map(json.loads, f)


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--out",
        type=Path,
        default=ROOT / "rationale_eval" / "results" / "rationales_input.parquet",
    )
    ap.add_argument(
        "--dataset", default="toloka/primeape", help="Primeape on the Hugging Face Hub"
    )
    ap.add_argument(
        "--judge-outputs",
        type=Path,
        default=ROOT / "judge_outputs" / "sample.jsonl",
        help="a JSONL file of judge outputs, or a folder with one subfolder per condition",
    )
    args = ap.parse_args()

    human = human_table(args.dataset)
    rows = []
    for setup in SETUPS:
        for r in records(args.judge_outputs, setup):
            assert not r["swapped"]
            h = human[
                (
                    r["language"],
                    r["id"],
                    frozenset([r["generator_a"], r["generator_b"]]),
                )
            ]
            assert (
                h.generator_a == r["generator_a"]
            ), "rationale conditions use the benchmark order"
            text = r["response"]
            if r["criterion"] is None:
                segs = (
                    segment_combined(text)
                    if isinstance(text, str)
                    else dict.fromkeys(CRITERIA, "")
                )
                crits = CRITERIA
            else:
                crits = [r["criterion"]]
                segs = {
                    r["criterion"]: (
                        segment_separated(text, r["criterion"])
                        if isinstance(text, str)
                        else ""
                    )
                }
            for c in crits:
                rationale = segs[c] if status(text, segs[c]) != "over_length" else ""
                verdict, label = r["predicted"].get(c), getattr(h, f"{c}_preference")
                rows.append(
                    {
                        "setup": setup,
                        "lang": r["language"],
                        "judge": JUDGE_NAMES[r["judge"]],
                        "crit": c,
                        "instr": r["id"],
                        "pair": "|".join(sorted([r["generator_a"], r["generator_b"]])),
                        "judge_verdict": verdict,
                        "human_label": label,
                        "verdict_valid": verdict is not None,
                        "verdict_correct": verdict == label,
                        "rationale": rationale,
                        "rationale_status": status(text, segs[c]),
                        "rationale_words": len(rationale.split()),
                        "human_rationale": " ".join(
                            str(getattr(h, f"{c}_explanation")).split()
                        ),
                    }
                )
    df = pd.DataFrame(rows)
    df.insert(
        0,
        "row_id",
        [
            hashlib.sha1("|".join(map(str, k)).encode()).hexdigest()[:16]
            for k in df[["setup", "lang", "judge", "crit", "instr", "pair"]].itertuples(
                index=False
            )
        ],
    )
    assert df.row_id.is_unique
    args.out.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(args.out, index=False)
    print(f"wrote {len(df):,} rows -> {args.out}")
    print(
        df.groupby(["setup", "rationale_status"])
        .size()
        .unstack(fill_value=0)
        .to_string()
    )
    print("\nmedian rationale words (status ok):")
    print(
        df[df.rationale_status == "ok"]
        .groupby(["setup", "lang"])
        .rationale_words.median()
        .unstack()
        .to_string()
    )


if __name__ == "__main__":
    main()
