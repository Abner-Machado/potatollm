# potatollm

will this model run on your potato?

| date | model | quant | size GB | RAM GB | tokens | seconds | tok/s | min free RAM GB | peak pagefile GB | paged |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-08-20 | qwen3:4b | Q4_K_M | 2.326 | 7.681 | 120 | 15.566 | 7.709 | 0.017 | 15.413 | yes |
| 2026-08-20 | qwen3:4b | Q4_K_M | 2.326 | 7.681 | 120 | 16.314 | 7.356 | 0.096 | 15.608 | yes |
| 2026-08-20 | qwen2.5:1.5b | Q4_K_M | 0.918 | 7.681 | 120 | 5.946 | 20.181 | 0.015 | 16.581 | yes |
| 2026-09-21 | llama3.2:1b | Q8_0 | 1.23 | 7.681 | 120 | 8.107 | 14.802 | 0.013 | 13.579 | yes |
| 2026-11-13 | Huihui-Qwen3-4B-Instruct-2507-abliterated:Q4_K_M | Q4_K_M | 2.326 | 23.681 | 120 | 15.59 | 7.697 | 9.252 | 17.725 | yes |
| 2026-11-13 | LFM2.5-8B-A1B-abliterated-v3:Q4_K_M | Q4_K_M | 4.801 | 23.681 | 84 | 4.451 | 18.874 | 7.863 | 19.036 | yes |
| 2026-11-13 | hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-i1-GGUF:i1-IQ2_XXS | IQ2_XXS | 8.845 | 23.681 | 120 | 17.862 | 6.718 | 3.637 | 23.655 | yes |

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

- Python 3.11 or newer (CI covers 3.11 and 3.13; the tool still starts on 3.9, that is just no longer tested)
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

## Real-world calibration (this machine: i3-1215U, no GPU, 7.68 GB RAM at the time)

| model | size | verdict | outcome |
|-------|------|---------|---------|
| qwen3:4b (Q4_K_M) | 2.33 GB | tight fit | 7.7 tok/s, completed in 15.6 s |
| llama3.2:1b (Q8_0) | 1.23 GB | fits comfortably | 14.8 tok/s, completed in 8.1 s |
| qwen3-abliterated:8b | 4.68 GB | do not try | did not complete 120 tokens in 10 minutes; free RAM 0.07 GB, pagefile 9.5 GB |

The 1b model at Q8_0 is slower than qwen2.5:1.5b at Q4_K_M (14.8 vs 20.2 tok/s) even with
fewer parameters: on a machine this tight the file size on disk decides more than the
parameter count, because everything above free RAM goes to the pagefile.

The 4b model is the reference "runs" case. The 8b model is the reference "do not try" case — it does not finish in reasonable time and puts the machine into heavy paging.

## MoE vs dense on a potato

Three rows dated 2026-11-13, same i3-1215U as every row above, but now with 23.68 GB of RAM
instead of 7.68 GB. I wanted to know whether a mixture-of-experts model with 3B active
parameters would beat a 4B dense model on a CPU. It did not. It lost to both models that
were already sitting on the disk.

The exact weights, so the rows can be reproduced:

| model | GGUF quant | file on disk | params | tok/s |
|-------|-----------|--------------|--------|-------|
| `Huihui-Qwen3-4B-Instruct-2507-abliterated` | `Q4_K_M` | 2.326 GB | 4B dense | 7.697 |
| `LFM2.5-8B-A1B-abliterated-v3` | `Q4_K_M` | 4.801 GB | 8B total, 1B active | 18.874 |
| `hf.co/mradermacher/Huihui-Qwen3.6-35B-A3B-abliterated-i1-GGUF` | `i1-IQ2_XXS` | 8.845 GB | 35B total, 3B active | 6.718 |

The middle row is the headline. A MoE with 1B active parameters runs 2.5 times faster than a
dense 4B, off a file twice the size. Active parameters set the speed, total size sets the
RAM. That part of the theory holds.

The bottom row is where it breaks. This machine reads memory at about 20 GB/s. At roughly
2.17 bits per weight, 3B active parameters means around 0.81 GB pulled per token, so the
usual `tok/s = bandwidth / bytes per token` arithmetic predicts 24 tok/s. The measurement
came back at 6.718, off by a factor of 3.6. I reran it by hand twice outside the fixed
prompt and got 6.55 and 6.96, so it is not a sampling artifact.

Two things explain the gap, and the first one matters more than the architecture:

The first is that IQ quantization is compute-bound rather than bandwidth-bound. Unpacking an i-quant weight costs
far more arithmetic per byte than a K-quant one. On a 6-core i3 the dequantization kernel
becomes the ceiling before memory does, which is how a 2.326 GB `Q4_K_M` file ends up tied
with an 8.845 GB `IQ2_XXS` one. The practical consequence is the opposite of intuition:
moving up to `IQ3_XS` would be slower, not faster. If you want speed on hardware like this,
a small K-quant beats a large i-quant, and the quant family belongs in the comparison
alongside the file size.

The second is that a MoE reads its experts in scattered chunks. The 20 GB/s figure comes from sequential reads.
Gathering a different subset of experts per token does not look like a sequential read, and
the LFM2.5 row shows the same tax in milder form: 18.874 against a prediction near 28.

There is one more cost that the fixed prompt hides. The A3B is a reasoning model. Asked
outside the benchmark for an answer in 120 words or fewer, it emitted 1530 tokens of chain
of thought and took 4 minutes 7 seconds of wall clock. Equal tok/s does not mean an equal
wait for a usable answer.

### What the RAM columns actually say

The upgrade from 7.68 GB to 23.68 GB is visible in one column and invisible in another.
`min free RAM` went from 0.013 to 0.096 GB on the old rows to between 3.637 and 9.252 GB on
the new ones. The machine stopped being starved. Speed barely moved: `qwen3:4b` at `Q4_K_M`
did 7.709 tok/s on 7.68 GB and the 4B abliterated at the same quant and the same file size
does 7.697 on 23.68 GB. More RAM bought headroom, not throughput, which is what you would
expect once a model already fits.

Read `paged` with that in mind. The flag trips when pagefile usage climbs more than 0.25 GB
during a run, and on Windows that number is systemwide commit charge rather than proof of
disk thrashing. Loading an 8.845 GB model raises commit by roughly its own size even when
every byte stays resident. With 9.252 GB still free at the low point, the 4B row is not
swapping. `min free RAM` is the column that tells you whether the machine was actually
starved, and `peak pagefile` climbing to 23.655 GB on the A3B row with 3.637 GB free is the
honest warning sign on this set: that model is the first one here that made the pagefile the
thing to watch.

One caveat I will not paper over. `IQ2_XXS` is a 2-bit quantization and an aggressive one.
It is fine for measuring speed, which is all this table claims, and it is not a verdict on
how well the 35B model reasons at a sane quant. What I can say is that no quant of it is
going to be fast here, because the bottleneck is not the one the file size suggests.

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
