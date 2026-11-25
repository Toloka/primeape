# Human evaluation of NLI verdict recovery

Self-consistency (SC) and human-label agreement (HA) in [`rationale_eval/`](../rationale_eval/) rely on NLI to recover the verdict expressed in a rationale. To validate this recovery, annotators labeled 465 rationales in English, Norwegian Bokmål, and Urdu with the preference each one expresses, following the [annotation guidelines](../guidelines/human_nli_evaluation.md). Annotators saw only the rationale, not the instruction or the responses.

[`annotations.jsonl`](annotations.jsonl) has one line per rationale:

| Language | Judge rationales | Human rationales | Labeled by both annotators |
|:--|--:|--:|--:|
| English (`en`) | 130 | 25 | 45 |
| Norwegian Bokmål (`nb`) | 130 | 25 | 45 |
| Urdu (`ur`) | 130 | 25 | 45 |

## Annotation

Two annotators worked on each language: native speakers of Norwegian Bokmål and Urdu, and fluent speakers of English. Each labeled 100 rationales: 55 alone and 45 judge rationales that both annotators labeled, to measure their agreement. For each rationale, they chose the preference it expresses (A, B, Tie, or "Can't tell" when none can be inferred) and could flag rationales whose reasoning contradicts their stated conclusion. Before the main items, they completed seven English training checks with feedback; the training answers are not included.

* **Judge rationales** come from the JOINT+R and CRITERION+R conditions, with a valid verdict and 3–120 words. They are drawn in equal numbers (15–17 per language) for each combination of condition, verdict correctness (`judge_verdict` = `human_label`), and NLI confidence (`nli_max_entailment` ≥ 0.5), spread over criteria and judges, with at most one rationale per comparison and criterion.
* **Human rationales** come from Primeape, with 3–120 words, balanced over the human labels (8–9 per label and language), and from comparisons and criteria not used for the judge rationales.


## Record format

```json
{
  "item_id": "en-047",
  "language": "en",
  "source": "judge",
  "condition": "criterion_r",
  "judge": "openai/gpt-5",
  "id": "5a9b3708cc56be2c931b20dce76c768c",
  "generator_a": "openai/gpt-4-0613",
  "generator_b": "anthropic/claude-3-opus-20240229",
  "criterion": "relevance",
  "rationale": "Response A includes some taxa that are not extinct (e.g., Hokkaido/Kamchatka brown bears) or are dubious, reducing relevance. Response B lists recognized extinct species/subspecies accurately.",
  "human_label": "A",
  "judge_verdict": "B",
  "nli_verdict": "tie",
  "nli_max_entailment": 0.0126,
  "annotations": [
    {"answer": "B", "self_contradiction": false, "note": ""},
    {"answer": "B", "self_contradiction": false, "note": ""}
  ]
}
```

* `item_id`: the item's identifier in this file.
* `language`: `en`, `nb`, or `ur`.
* `source`: `judge` for a judge rationale, `human` for a human rationale from Primeape.
* `condition`: `joint_r` (JOINT+R) or `criterion_r` (CRITERION+R); `null` for human rationales.
* `judge`: the judge's OpenRouter ID; `null` for human rationales.
* `id`, `generator_a`, `generator_b`: the comparison, as in [`judge_outputs/`](../judge_outputs/README.md#record-format): the instruction id in Primeape and the generators of Response A and Response B.
* `criterion`: the criterion the rationale is about.
* `rationale`: the text shown to the annotators. Judge rationales are extracted from the judge's `response` as described in [`rationale_eval/`](../rationale_eval/README.md#rationale-extraction).
* `human_label`: the human preference in Primeape (`A`, `B`, `tie`). For a human rationale, it is the label that the rationale justifies.
* `judge_verdict`: the judge's verdict extracted by the parser; `null` for human rationales.
* `nli_verdict`: the verdict implied by NLI (`implied_verdict` in `rationale_eval/`), i.e., the hypothesis with the highest entailment probability; `null` for human rationales.
* `nli_max_entailment`: that highest entailment probability (`implied_max_entail`); `null` for human rationales.
* `annotations`: one annotation for most rationales and two for those labeled by both annotators:
  * `answer`: `A`, `B`, `tie`, or `cant_tell` ("Can't tell").
  * `self_contradiction`: `true` if the annotator flagged that the reasoning contradicts the stated conclusion; `answer` then records the stated conclusion.
  * `note`: the annotator's optional note, e.g., on ungrammatical text; empty if none.

## Usage

See [Usage](../README.md#usage) in the main README for an example that loads the file.
