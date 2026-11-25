"""Run judge models on prompts from TSV files through an OpenAI-compatible API.

Each input TSV needs a `combined_prompt` column. Results are appended to a JSONL file,
one line per input line and model; a rerun skips the pairs already in the output.
"""

import argparse
import asyncio
import csv
import json
import os
from typing import Iterator

import openai
from tqdm.asyncio import tqdm


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(
            f"Error: environment variable {name} is not set. "
            "Set OPENAI_API_KEY and OPENAI_BASE_URL and try again."
        )
    return value


CLIENT = openai.AsyncClient(
    api_key=require_env("OPENAI_API_KEY"),
    base_url=require_env("OPENAI_BASE_URL"),
)


def get_items(file: str) -> Iterator[dict]:
    with open(file) as f:
        cols = [col.strip() for col in next(iter(f)).split("\t")]
        reader = csv.DictReader(f, cols, delimiter="\t")
        for line, item in enumerate(reader):
            yield {
                "file": file,
                "line": line,
                "combined_prompt": item["combined_prompt"],
            }


MAX_COMPLETION_TOKENS = {
    "microsoft/phi-4": 8192,
    "qwen/qwen-2.5-72b-instruct": 16384,
    "qwen/qwen-2.5-7b-instruct": 32768,
    "qwen/qwen3-32b": 16384,
}


async def process(
    *,
    file2models: dict[str, list[str]],
    output_path: str,
    concurrency: int,
    timeout: float,
):
    processed: set[tuple[str, int, str]] = set()
    if os.path.exists(output_path):
        with open(output_path) as f:
            for line in f:
                item = json.loads(line)
                key = (item["file"], item["line"], item["model"])
                processed.add(key)

    semaphore = asyncio.Semaphore(concurrency)
    tasks = []

    async def _process(item: dict, model: str):
        key = (item["file"], item["line"], model)
        if key in processed:
            return
        while True:
            try:
                async with semaphore:
                    response = await CLIENT.chat.completions.create(
                        messages=[
                            {
                                "role": "user",
                                "content": item["combined_prompt"],
                            }
                        ],
                        model=model,
                        max_completion_tokens=MAX_COMPLETION_TOKENS.get(model, 65536),
                        timeout=timeout,
                    )
                content = response.choices[0].message.content
                assert isinstance(content, str)
                break
            except Exception as e:
                print(model, e)
                await asyncio.sleep(10)
        result = {
            "file": item["file"],
            "line": item["line"],
            "model": model,
            "response": content,
        }
        with open(output_path, mode="a") as f:
            print(json.dumps(result, ensure_ascii=False), file=f, flush=True)

    for file, models in file2models.items():
        for item in get_items(file):
            for model in models:
                tasks.append(_process(item, model))

    await tqdm.gather(*tasks)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "input", help="JSON file mapping input TSV paths to lists of models"
    )
    parser.add_argument("output", help="JSONL file to append results to")
    parser.add_argument(
        "-c", "--concurrency", type=int, default=128, help="max concurrent requests"
    )
    parser.add_argument(
        "-t",
        "--timeout",
        type=float,
        default=300,
        help="per-request timeout in seconds",
    )
    args = parser.parse_args()

    with open(args.input) as f:
        file2models = json.load(f)
    asyncio.run(
        process(
            file2models=file2models,
            output_path=args.output,
            concurrency=args.concurrency,
            timeout=args.timeout,
        )
    )


if __name__ == "__main__":
    main()
