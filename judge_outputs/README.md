# Judge outputs

The results in our paper rely on 396,900 judge calls: the raw outputs of the twelve judges in every evaluation condition, with the verdicts extracted by [`parsers/judge_parser.py`](../parsers/judge_parser.py) and the human labels from [Primeape](https://huggingface.co/datasets/toloka/primeape). The complete judge outputs are not part of this repository; we provide them upon request (see [Contact us](../README.md#contact-us)). This folder contains:

* [`sample.jsonl`](sample.jsonl): a sample of 1,260 judge calls in the format of the complete outputs;
* one folder per condition with judge calls, whose `README.md` lists the prompts of every language;
* [`run_judges.py`](run_judges.py) and [`judges.example.json`](judges.example.json): the script for querying the judges and an example of its configuration (see [Running judges](#running-judges)).

## Evaluation conditions

The paper defines seven evaluation conditions. Five of them require judge calls:

| Folder | Condition | Description | Prompts | Judge calls |
|:--|:--|:--|:--|--:|
| [`joint/`](joint/) | JOINT | all five criteria in one call | P0–P2 | 79,380 |
| [`joint_r/`](joint_r/) | JOINT+R | as JOINT, with a rationale before each criterion's verdict | selected | 26,460 |
| [`criterion/`](criterion/) | CRITERION | one criterion per call | selected, per criterion | 132,300 |
| [`criterion_r/`](criterion_r/) | CRITERION+R | as CRITERION, with a rationale before the verdict | selected, per criterion | 132,300 |
| [`position_bias/`](position_bias/) | POSITION BIAS | as JOINT, with responses A and B swapped | selected | 26,460 |

One prompt applied to the 2,205 comparisons by the twelve judges amounts to 26,460 calls; JOINT uses three prompts, and CRITERION and CRITERION+R need one call per criterion. The selected prompt is P1 for English, Norwegian, Spanish, Urdu and Yoruba, and P0 for French and Hindi.

The other two conditions need no further judge calls. Both pair each judge's JOINT verdicts (selected prompt) with its POSITION BIAS verdicts on the same comparison, so that every comparison is judged in both response orders:

* LENGTH BIAS uses all comparisons to test whether a judge favors the longer response more often than the human annotators do.
* SELF-PREFERENCE uses the comparisons that contain a response by a generator from the judge's own model or model family, to test whether the judge favors these responses more than the human annotators and the control judges do.

## Sample

[`sample.jsonl`](sample.jsonl) holds all 180 judge calls for one comparison in each of the seven languages: the twelve judges under the three JOINT prompts, JOINT+R, POSITION BIAS, and the five criteria of CRITERION and CRITERION+R. The seven comparisons belong to the same instruction ("what is the color of mars", `id` `34e64082e137d600f29bb3eba8375540`) and its translations. The sample includes outputs from which no verdict could be extracted (`missing`, `unparseable_value`, `conflicting_verdicts`, and `over_length_limit` in `parser_status`).

## Judges

The twelve judges, their OpenRouter IDs (the values of `judge`) and their licenses are listed in the [main README](../README.md#judge-outputs). See Appendix F.1 of the paper for the inference settings.

## Running judges

[`run_judges.py`](run_judges.py) sends each prompt to the judges through an OpenAI-compatible API; we used [OpenRouter](https://openrouter.ai). Set `OPENAI_API_KEY` to your API key and `OPENAI_BASE_URL` to the API's address (`https://openrouter.ai/api/v1` for OpenRouter), then run:

```bash
python judge_outputs/run_judges.py judges.json outputs.jsonl
```

**Input.** Each input file is a TSV with a header row and one judge call per row. The script reads only the `combined_prompt` column, which holds the complete prompt: a prompt from the condition's `README.md` with `{instruction}`, `{output_a}` and `{output_b}` filled in from Primeape. Other columns, such as `id`, `generator_a` and `generator_b`, are ignored, but they let you match the outputs to the comparisons. A JSON file maps each TSV to the OpenRouter IDs of the judges to run on it, as in [`judges.example.json`](judges.example.json).

**Output.** The script appends one line per row and judge to the output file:

```json
{"file": "path/to/inputs.tsv", "line": 0, "model": "qwen/qwen3-32b", "response": "1. Relevance Preference: A\n\n2. Naturalness Preference: Tie\n[...]"}
```

`line` is the 0-based index of the row in the TSV, not counting the header. `response` is the raw completion; [`parsers/judge_parser.py`](../parsers/judge_parser.py) extracts the verdicts from it.

**Settings.** The requests set no sampling parameters, so the provider's defaults apply. The maximum output length is 65,536 tokens, except for Qwen2.5-7B (32,768), Qwen2.5-72B (16,384) and Qwen3-32B (16,384). Up to 128 requests run at once (`--concurrency`), each with a timeout of 300 seconds (`--timeout`). Failed requests are retried every 10 seconds; a rerun skips the rows and judges already in the output file.

## Record format

Each line is one judge call:

```json
{
  "condition": "criterion_r",
  "id": "34e64082e137d600f29bb3eba8375540",
  "language": "en",
  "prompt": "p1",
  "criterion": "safety",
  "judge": "meta-llama/llama-3.1-8b-instruct",
  "generator_a": "meta-llama/Meta-Llama-3-70B-Instruct",
  "generator_b": "allenai/tulu-2-dpo-70b",
  "swapped": false,
  "response": "Response A is more detailed and informative, [...]\n\nSafety: B",
  "predicted": {"safety": "B"},
  "parser_status": {"safety": "valid"},
  "parser_evidence": {"safety": [{"line": 5, "end_line": 5, "text": "Safety: B"}]},
  "ground_truth": {"safety": "tie"}
}
```

* `condition`: the evaluation condition (`joint`, `joint_r`, `criterion`, `criterion_r`, `position_bias`). The complete outputs have one file per condition and language (`<condition>/<language>.jsonl`) instead of this field.
* `id`: the instruction id in Primeape. Together with the two generators, it identifies the comparison: `(id, {generator_a, generator_b})` matches exactly one row of the benchmark's configuration for `language`.
* `language`: the benchmark configuration (`en`, `fr`, `hi`, `nb`, `es`, `ur`, `yo`).
* `prompt`: the prompt variant (`p0`, `p1`, `p2`). In CRITERION and CRITERION+R, it is the selected variant from which the per-criterion prompts are adapted; the prompts themselves are listed in the folder's `README.md`.
* `criterion`: the criterion evaluated in the call; `null` in the joint conditions, where one call covers all five criteria.
* `judge`: the judge model's OpenRouter ID.
* `generator_a`, `generator_b`: the generators of Response A and Response B, in the order shown to the judge.
* `swapped`: `true` if the responses are shown in the reverse of the benchmark's order (POSITION BIAS only).
* `response`: the judge's full completion. It is `null` for two calls in which the API returned an empty response.
* `predicted`: the extracted verdict per criterion: `A`, `B`, `tie`, or `null` if none could be extracted.
* `parser_status`: why a verdict was or was not extracted: `valid`, `missing`, `unparseable_value`, `conflicting_verdicts`, `over_length_limit` (completions over 10,000 characters, mostly runaway generations), `empty_or_nontext`, `invalid_json`.
* `parser_evidence`: the lines of `response` that the parser used for each criterion.
* `ground_truth`: the human preference per criterion (`A`, `B`, `tie`), in the order shown to the judge, so it is flipped relative to the benchmark when `swapped` is `true`.

`predicted`, `parser_status` and `parser_evidence` are reproduced by `judge_parser.parse(response, criterion)`.
