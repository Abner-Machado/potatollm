# potatollm

will this model run on your potato?

| date | model | quant | size GB | RAM GB | tokens | seconds | tok/s | min free RAM GB | peak pagefile GB | paged |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-08-20 | qwen3:4b | Q4_K_M | 2.326 | 7.681 | 120 | 15.566 | 7.709 | 0.017 | 15.413 | yes |
| 2026-08-20 | qwen3:4b | Q4_K_M | 2.326 | 7.681 | 120 | 16.314 | 7.356 | 0.096 | 15.608 | yes |
| 2026-08-20 | qwen2.5:1.5b | Q4_K_M | 0.918 | 7.681 | 120 | 5.946 | 20.181 | 0.015 | 16.581 | yes |

potatollm answers one practical question: can this Ollama model run on a low-RAM CPU-only computer, and at what real speed?

It has two stages:

1. `check <model>`: reads local RAM and model metadata without pulling the model, then prints a fit verdict.
2. `bench <model>`: runs one fixed prompt through local Ollama and writes a comparable JSON result.

The JSON result is the source of truth for the table. Do not edit benchmark rows by hand; run the CLI and regenerate the table.

## Install

Download these files into one folder and run them there:

- `potatollm.py`
- `potatollm.cmd`
- `schema.json`

Requirements:

- Python 3.9 or newer
- Ollama running locally for `bench`
- No Python packages to install

On Windows, double-click `potatollm.cmd` or run commands from a terminal:

```bat
potatollm.cmd selftest
potatollm.cmd check qwen3:4b
potatollm.cmd bench qwen3:4b
potatollm.cmd table
```

On Linux or macOS:

```sh
python potatollm.py selftest
python potatollm.py check qwen3:4b
python potatollm.py bench qwen3:4b
python potatollm.py table
```

## Commands

### `selftest`

Checks the local chain without pulling any model:

- Python version
- RAM and pagefile/swap detection
- Ollama API ping
- JSON write and Markdown table conversion

It exits with code 0 only when every item passes.

### `check <model>`

Reads machine RAM and model size/quantization metadata. It tries local Ollama first. If the model is not listed locally, it reads public metadata from ollama.com.

Verdicts (based on total RAM, not free RAM):

- `fits comfortably` — model size ≤ 22% of total RAM
- `tight fit` — model size ≤ 35% of total RAM (runs, but leave headroom)
- `will page` — model size ≤ 50% of total RAM (will swap, slow)
- `do not try` — model size > 50% of total RAM (will thrash or OOM)

A separate warning line prints when current free RAM is low: `RAM free now: X — close programs before running`.

Bad verdicts include a smaller-model suggestion (only from models that actually exist in local Ollama).

### `bench <model>`

Runs a real local Ollama benchmark using the fixed prompt embedded in `potatollm.py`.

It records:

- generated tokens
- duration
- tokens per second
- lowest free RAM observed
- highest pagefile/swap usage observed
- whether paging was detected

Automatic abort: if free RAM stays below 0.15 GB for more than 20 seconds, the benchmark aborts and reports `aborted: thrashing detected` with the numbers at that moment, writing the JSON with that status. Default timeout is 300 seconds.

This command never pulls models. If the model is missing, it prints a clear error.

### `table`

Reads `results/*.json` and prints a Markdown table, ignoring `selftest-example` rows.

## Result JSON

Every result follows `schema.json` (version 2.0) and includes:

- `schema_version`
- `date`
- `model`
- `quantization`
- `size_gb`
- `backend`
- `backend_version`
- `cpu`
- `ram_total_gb`
- `os`
- `prompt_id`
- `generated_tokens`
- `duration_s`
- `tok_s`
- `min_free_ram_gb`
- `peak_pagefile_gb`
- `paged`
- `status`

If a field cannot be detected, it is written as `"unknown"` explicitly — never guessed.

## Contribute a result

The table above is the point of this project. One machine is one data point; the
table is only useful once it covers machines other than mine.

To add yours:

1. Run the benchmark on your own machine:

   ```sh
   python potatollm.py bench <model>
   ```

   This writes a new file under `results/`.

2. Regenerate the table:

   ```sh
   python potatollm.py table
   ```

3. Open a pull request with **both** the new `results/*.json` file and the updated
   table in this README.

Rules, so that rows stay comparable:

- Do not edit table rows by hand. The JSON is the source of truth; `table` renders it.
- Do not submit a run with `status` other than `ok` as a speed measurement. An
  `aborted: thrashing detected` result is still welcome — it is evidence that the
  model does not run there — but it belongs in the table as exactly that.
- Keep `prompt_id` as produced by the tool. A row generated from a different prompt
  is not comparable to the others.
- `unknown` is a valid field value. Leave it as written rather than filling it in by
  hand.

Low-RAM and CPU-only machines are the interesting cases. A row proving that a model
does *not* run is worth as much as one proving that it does.

## Real-world calibration (this machine: i3-1215U, 7.68 GB RAM, no GPU)

| model | size | verdict | outcome |
|-------|------|---------|---------|
| qwen3:4b (Q4_K_M) | 2.33 GB | tight fit | 7.7 tok/s, completed in 15.6 s |
| qwen3-abliterated:8b | 4.68 GB | do not try | did not complete 120 tokens in 10 minutes; free RAM 0.07 GB, pagefile 9.5 GB |

The 4b model is the reference "runs" case. The 8b model is the reference "do not try" case — it does not finish in reasonable time and puts the machine into heavy paging.

## How this was built

Specified, written and reviewed by AI models under human direction: architecture, review and
verification by Claude (Opus 5), implementation by Hermes (gpt-5.5 via Codex), English
translation of the foundation document by DeepSeek V4 Flash. Direction and final say by the
repo owner.

The model that wrote the code reported "implemented and verified" while shipping two fatal
defects — `selftest` claimed Ollama was responding while the server was switched off, and
`check` gave the same verdict to a model that runs and one that does not finish. Both were
caught by running the tool, not by reading it. See [FOUNDATION.md](FOUNDATION.md) for the
full account.

## License

MIT License

Copyright (c) 2026 Abner Machado

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
