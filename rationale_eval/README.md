# Rationale evaluation

Evaluates the rationales that judges write in the two rationale conditions (JOINT+R and CRITERION+R) against the human rationales in Primeape and against the judges' own verdicts (§4 and Appendix F.5 of the paper).

| Script | What it does |
|:--|:--|
| [`prepare_rationales.py`](prepare_rationales.py) | extracts one rationale per judge, comparison and criterion from [`judge_outputs/`](../judge_outputs/) and pairs it with the human label and rationale |
| [`rationale_eval.py`](rationale_eval.py) | computes the similarity and NLI metrics (a GPU or Apple MPS is recommended) |
| [`aggregate.py`](aggregate.py) | aggregates the row-level results per judge, condition, language and verdict correctness |
| [`mask_verdicts.py`](mask_verdicts.py) | masks verdict statements in the rationales and recomputes the NLI-implied verdict (Appendix F.5) |
| [`tie_hypothesis_check.py`](tie_hypothesis_check.py) | compares alternative NLI hypotheses for Tie on the human rationales (Appendix F.5) |

## Workflow

Install the dependencies with `pip install -r requirements.txt`, and run all commands from the repository root. Every result is written to `rationale_eval/results/`.

1. **Prepare (CPU).** Loads the judge outputs and the human rationales from [`toloka/primeape`](https://huggingface.co/datasets/toloka/primeape). By default, the judge outputs are the sample in [`judge_outputs/sample.jsonl`](../judge_outputs/sample.jsonl):

   ```bash
   python rationale_eval/prepare_rationales.py      # -> results/rationales_input.parquet (840 rows)
   ```

   The results in the paper use the complete judge outputs, which we provide upon request. Place them in `judge_outputs/<condition>/<language>.jsonl` and pass `--judge-outputs judge_outputs` (264,600 rows).

2. **Run the evaluation.** All comparisons, with cross-lingual NLI:

   ```bash
   python rationale_eval/rationale_eval.py --input rationale_eval/results/rationales_input.parquet \
       --out rationale_eval/results/crosslingual
   ```

3. **Aggregate.**

   ```bash
   python rationale_eval/aggregate.py                # -> results/aggregates/*.csv
   ```

4. **Verdict masking and Tie hypotheses (Appendix F.5).** Masking recomputes the NLI-implied verdict on the masked judge and human rationales:

   ```bash
   python rationale_eval/mask_verdicts.py prepare
   for m in m1 m2 human_m2; do
       python rationale_eval/rationale_eval.py --input rationale_eval/results/masked/input_$m.parquet \
           --out rationale_eval/results/masked/$m --stages nli_verdict
   done
   python rationale_eval/mask_verdicts.py analyze
   python rationale_eval/tie_hypothesis_check.py
   ```

## Rationale extraction

* **CRITERION+R:** the rationale is the whole output except the verdict line(s).
* **JOINT+R:** each criterion's rationale is the text after its label ("**Relevance**: Response B is better ...") or heading, or a prose paragraph introducing it ("For Relevance, ..."), up to the next criterion, heading or separator. Short labelled lines ("- Relevance: A") are verdicts, not rationales.

`rationale_status` is `ok` (at least three words), `empty`, `no_response` or `over_length` (more than 10,000 characters, as in the verdict parser). Only `ok` rows are scored; rationale presence (the share of `ok`) is reported per judge. On the paper's data, 93% of JOINT+R and 99% of CRITERION+R rationales are `ok`.

## Metrics

All metrics are computed per rationale (judge × comparison × criterion × condition).

| Metric | Column | What it measures |
|:--|:--|:--|
| chrF++ | `chrf` | character n-gram overlap with the human rationale |
| Embedding similarity | `embed_cosine` | cosine similarity of the LaBSE embeddings of the judge and human rationales |
| Implied verdict | `implied_verdict` | the hypothesis with the highest entailment probability: "Response A is better than Response B.", "Response B is better than Response A.", or "Response A and Response B are equally good." |
| Self-consistency (SC) | `implied_verdict` = `judge_verdict` | the implied verdict equals the judge's own verdict |
| Human-label agreement (HA) | `implied_verdict` = `human_label` | the implied verdict equals the human label |
| NLI support | `nli_support` | mean entailment probability of each judge sentence given the human rationale |
| NLI contradiction | `nli_contra` | mean contradiction probability of each judge sentence given the human rationale |
| NLI coverage | `nli_coverage` | mean entailment probability of each human sentence given the judge rationale |
| NLI validation | `rows/nli_validation_*` | the implied-verdict procedure applied to the human rationales and compared with the human labels; it checks how reliably NLI recovers the verdict from a rationale in each language |

NLI is cross-lingual: a multilingual mDeBERTa NLI model is applied to the original texts with English hypotheses, and NLI columns carry the suffix `_crosslingual`. `aggregate.py` reports SC and HA class-balanced (the mean of the per-class rates over A, B and Tie) and excludes Yoruba from the NLI metrics, where NLI does not reliably recover the human labels from the human rationales.

Models: `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` (NLI) and `sentence-transformers/LaBSE` (embeddings). Each can be overridden on the command line (`--nli-model`, `--embed-model`).

## Outputs

```
rationale_eval/results/
├── rationales_input.parquet        prepare_rationales.py
├── crosslingual/                   rationale_eval.py
│   ├── run_config_<timestamp>.json arguments, models and hypotheses of each run
│   ├── rows_merged.parquet         every input row with all row-level metrics
│   └── rows/<stage>/part-*.parquet shards (resume state; nli_validation is read by the later scripts)
├── aggregates/                     aggregate.py
├── masked/                         mask_verdicts.py
└── tie_hypothesis/                 tie_hypothesis_check.py
```
