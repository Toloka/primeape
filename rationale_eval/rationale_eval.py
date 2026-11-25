from __future__ import annotations

import argparse
import hashlib
import os
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

# Apple-silicon GPUs (MPS): run the rare unsupported operations on the CPU instead of failing
os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")

DEFAULT_STAGES = [
    "surface",
    "embed",
    "nli_verdict",
    "nli_validation",
    "nli_agreement",
    "merge",
]
MODELS = {
    "nli": "MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7",
    "embed": "sentence-transformers/LaBSE",
}
MODE = "crosslingual"  # suffix of the NLI columns and shard folders
HYPOTHESES = {
    "A": "Response A is better than Response B.",
    "B": "Response B is better than Response A.",
    "tie": "Response A and Response B are equally good.",
}
VERDICTS = list(HYPOTHESES)
SENT_SPLIT = re.compile(r"(?<=[.!?।۔])\s+|\n+")
MAX_SENTENCES = 10


def log(msg: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {msg}", flush=True)


def sentences(text: str) -> list[str]:
    out = [s.strip() for s in SENT_SPLIT.split(text or "") if len(s.split()) >= 3]
    return out[:MAX_SENTENCES] or ([text.strip()] if text and text.strip() else [])


def device():
    """cuda (Colab) > mps (Apple silicon) > cpu."""
    import torch

    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def free_memory() -> None:
    import gc
    import torch

    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()
    elif torch.backends.mps.is_available():
        torch.mps.empty_cache()


def shards(df: pd.DataFrame, size: int):
    for k, start in enumerate(range(0, len(df), size)):
        yield k, df.iloc[start : start + size]


def lazy(factory):
    """Build a model only when a shard actually needs it (resumed runs skip loading)."""
    cache = []

    def get():
        if not cache:
            cache.append(factory())
        return cache[0]

    return get


def run_sharded(
    df: pd.DataFrame,
    out_dir: Path,
    size: int,
    fn,
    name: str,
    key: tuple[str, ...] = ("row_id",),
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    # shards are reused by position, so refuse to mix runs over different rows
    ids = hashlib.sha1(
        "\n".join(df[list(key)].astype(str).agg("|".join, axis=1)).encode()
    ).hexdigest()
    manifest = out_dir / "manifest.json"
    current = {"rows": len(df), "shard_size": size, "ids_sha1": ids}
    if manifest.exists() and json.loads(manifest.read_text()) != current:
        raise SystemExit(
            f"{out_dir} holds results for different rows or shard size; use a new --out folder"
        )
    manifest.write_text(json.dumps(current))
    total = (len(df) + size - 1) // size
    for k, part in shards(df, size):
        path = out_dir / f"part-{k:05d}.parquet"
        if path.exists():
            continue
        t0 = time.time()
        res = fn(part)
        tmp = path.with_suffix(".tmp")
        res.to_parquet(tmp, index=False)
        tmp.rename(path)
        log(
            f"{name}: shard {k + 1}/{total} ({len(part)} rows, {time.time() - t0:.0f}s)"
        )


def read_stage(out: Path, stage: str) -> pd.DataFrame | None:
    files = sorted((out / "rows" / stage).glob("part-*.parquet"))
    return (
        pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
        if files
        else None
    )


# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #


class NLI:
    """Batched NLI: returns probabilities [entailment, neutral, contradiction] per pair."""

    def __init__(self, name: str, batch_size: int, max_length: int = 512):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self.torch, self.dev = torch, device()
        self.tok = AutoTokenizer.from_pretrained(name)
        self.model = (
            AutoModelForSequenceClassification.from_pretrained(name).to(self.dev).eval()
        )
        if self.dev in ("cuda", "mps"):
            # fp16 on Apple M3 checked against fp32: 99.5% identical implied verdicts, |dp| <= 0.03
            self.model.half()
        labels = {v.lower(): int(k) for k, v in self.model.config.id2label.items()}
        self.idx = [labels["entailment"], labels["neutral"], labels["contradiction"]]
        self.batch_size, self.max_length = batch_size, max_length

    def __call__(self, premises: list[str], hypotheses: list[str]) -> np.ndarray:
        order = np.argsort([len(p) + len(h) for p, h in zip(premises, hypotheses)])
        out = np.zeros((len(premises), 3), dtype=np.float32)
        with self.torch.inference_mode():
            for start in range(0, len(order), self.batch_size):
                ids = order[start : start + self.batch_size]
                enc = self.tok(
                    [premises[i] for i in ids],
                    [hypotheses[i] for i in ids],
                    truncation=True,
                    max_length=self.max_length,
                    padding=True,
                    return_tensors="pt",
                ).to(self.dev)
                probs = self.torch.softmax(self.model(**enc).logits.float(), dim=-1)[
                    :, self.idx
                ]
                out[ids] = probs.cpu().numpy()
        return out


# --------------------------------------------------------------------------- #
# Stages
# --------------------------------------------------------------------------- #


def stage_surface(df: pd.DataFrame, out: Path, args) -> None:
    import sacrebleu

    def fn(part):
        return pd.DataFrame(
            {
                "row_id": part.row_id,
                "chrf": [
                    sacrebleu.sentence_chrf(j, [h], word_order=2).score / 100
                    for j, h in zip(part.rationale, part.human_rationale)
                ],
            }
        )

    run_sharded(df, out / "rows" / "surface", args.shard_size, fn, "surface")


def stage_embed(df: pd.DataFrame, out: Path, args) -> None:
    from sentence_transformers import SentenceTransformer

    model = lazy(lambda: SentenceTransformer(args.embed_model, device=device()))

    def fn(part):
        texts = list(dict.fromkeys(list(part.rationale) + list(part.human_rationale)))
        emb = model().encode(
            texts,
            batch_size=args.batch_size * 2,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        pos = {t: i for i, t in enumerate(texts)}
        cos = [
            float(emb[pos[j]] @ emb[pos[h]])
            for j, h in zip(part.rationale, part.human_rationale)
        ]
        return pd.DataFrame({"row_id": part.row_id, "embed_cosine": cos})

    run_sharded(df, out / "rows" / "embed", args.shard_size, fn, "embed")


def implied_verdicts(nli: NLI, premises: list[str]) -> pd.DataFrame:
    prem = [p for p in premises for _ in VERDICTS]
    hyp = [HYPOTHESES[v] for _ in premises for v in VERDICTS]
    probs = nli(prem, hyp).reshape(len(premises), len(VERDICTS), 3)
    res = pd.DataFrame(
        {f"p_entail_{v}": probs[:, k, 0] for k, v in enumerate(VERDICTS)}
    )
    res["implied_verdict"] = np.array(VERDICTS)[probs[:, :, 0].argmax(axis=1)]
    # below 0.5, no hypothesis is clearly entailed (the verdict is not decisive)
    res["implied_max_entail"] = probs[:, :, 0].max(axis=1)
    return res


def stage_nli_verdict(df: pd.DataFrame, out: Path, args) -> None:
    nli = lazy(lambda: NLI(args.nli_model, args.batch_size))

    def fn(part):
        res = implied_verdicts(nli(), list(part.rationale))
        res.insert(0, "row_id", part.row_id.values)
        return res

    run_sharded(
        df, out / "rows" / f"nli_verdict_{MODE}", args.shard_size, fn, "nli_verdict"
    )


def stage_nli_validation(df: pd.DataFrame, out: Path, args) -> None:
    human = df[
        ["lang", "crit", "instr", "pair", "human_label", "human_rationale"]
    ].drop_duplicates(["lang", "crit", "instr", "pair"])
    human = (
        human[human.human_rationale.str.split().str.len() >= 3]
        .sort_values(["lang", "crit", "instr", "pair"])
        .reset_index(drop=True)
    )
    nli = lazy(lambda: NLI(args.nli_model, args.batch_size))

    def fn(part):
        res = implied_verdicts(nli(), list(part.human_rationale))
        for col in ["lang", "crit", "instr", "pair", "human_label"]:
            res.insert(0, col, part[col].values)
        return res

    run_sharded(
        human,
        out / "rows" / f"nli_validation_{MODE}",
        args.shard_size,
        fn,
        "nli_validation",
        key=("lang", "crit", "instr", "pair"),
    )


def stage_nli_agreement(df: pd.DataFrame, out: Path, args) -> None:
    nli = lazy(lambda: NLI(args.nli_model, args.batch_size))

    def fn(part):
        prem, hyp, owner, kind = [], [], [], []
        for i, (j, h) in enumerate(zip(part.rationale, part.human_rationale)):
            for s in sentences(j):  # judge sentence given the human rationale
                prem.append(h)
                hyp.append(s)
                owner.append(i)
                kind.append(0)
            for s in sentences(h):  # human sentence given the judge rationale
                prem.append(j)
                hyp.append(s)
                owner.append(i)
                kind.append(1)
        probs = nli()(prem, hyp) if prem else np.zeros((0, 3))
        p = pd.DataFrame(
            {"owner": owner, "kind": kind, "ent": probs[:, 0], "con": probs[:, 2]}
        )
        sup = (
            p[p.kind == 0]
            .groupby("owner")
            .agg(nli_support=("ent", "mean"), nli_contra=("con", "mean"))
        )
        cov = p[p.kind == 1].groupby("owner").agg(nli_coverage=("ent", "mean"))
        res = pd.DataFrame(index=range(len(part))).join(sup).join(cov)
        res.insert(0, "row_id", part.row_id.values)
        return res

    run_sharded(
        df, out / "rows" / f"nli_agreement_{MODE}", args.shard_size, fn, "nli_agreement"
    )


# --------------------------------------------------------------------------- #
# Merge
# --------------------------------------------------------------------------- #


def stage_merge(df: pd.DataFrame, out: Path, args) -> None:
    """Join the row-level results of all stages into rows_merged.parquet."""
    rows = df.copy()
    for stage in ["surface", "embed", f"nli_verdict_{MODE}", f"nli_agreement_{MODE}"]:
        r = read_stage(out, stage)
        if r is not None:
            if stage.endswith(MODE):
                r = r.rename(
                    columns={c: f"{c}_{MODE}" for c in r.columns if c != "row_id"}
                )
            rows = rows.merge(r, on="row_id", how="left")
    rows.to_parquet(out / "rows_merged.parquet", index=False)
    log(f"merge: wrote rows_merged.parquet ({len(rows):,} rows)")


STAGES = {
    "surface": stage_surface,
    "embed": stage_embed,
    "nli_verdict": stage_nli_verdict,
    "nli_validation": stage_nli_validation,
    "nli_agreement": stage_nli_agreement,
    "merge": stage_merge,
}


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--stages", default=",".join(DEFAULT_STAGES))
    ap.add_argument("--nli-model", default=MODELS["nli"])
    ap.add_argument("--embed-model", default=MODELS["embed"])
    ap.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="default: 64 on a CUDA GPU, 8 on Apple silicon or CPU (fits 16 GB)",
    )
    ap.add_argument("--shard-size", type=int, default=5000)
    args = ap.parse_args()
    args.batch_size = args.batch_size or (64 if device() == "cuda" else 8)

    df = pd.read_parquet(args.input).sort_values("row_id").reset_index(drop=True)
    args.out.mkdir(parents=True, exist_ok=True)
    config = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "rows": len(df),
        **{k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
        "models": MODELS,
        "hypotheses": HYPOTHESES,
    }
    with open(
        args.out / f"run_config_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json", "w"
    ) as f:
        json.dump(config, f, indent=2)

    evaluable = df[df.rationale_status == "ok"].reset_index(drop=True)
    log(f"{len(df):,} rows, {len(evaluable):,} with a rationale; device={device()}")
    for stage in [s.strip() for s in args.stages.split(",") if s.strip()]:
        log(f"--- {stage}")
        # nli_validation also needs the human rationales of comparisons without a judge rationale
        STAGES[stage](
            df if stage in ("merge", "nli_validation") else evaluable, args.out, args
        )
        free_memory()


if __name__ == "__main__":
    main()
