# Contributing

The table in the README is the product. One machine is one data point, and a table
built on my laptop alone answers nothing for anyone else. Low-RAM and CPU-only
machines are the interesting cases here, and a row proving that a model does *not*
run is worth as much as a row proving that it does.

## Add a measurement

1. Install the tool and have Ollama running locally.

   ```sh
   uvx --from git+https://github.com/Abner-Machado/potatollm potatollm selftest
   ```

   `selftest` exits 0 only when Python, the memory counters, the Ollama ping and the
   JSON path all pass. Fix whatever it reports before benchmarking.

2. Pull the model you want to measure with Ollama, then run the benchmark. The tool
   never pulls a model for you.

   ```sh
   potatollm bench qwen3:4b
   ```

   This writes one JSON file. Running from a clone puts it in `results/`. Running an
   installed copy puts it in `results/` under your current directory, and
   `POTATOLLM_RESULTS` overrides both.

3. Copy that JSON into `results/` in your fork, regenerate the table, and paste the
   output over the table block at the top of the README.

   ```sh
   potatollm table
   ```

4. Open a pull request with both files changed: the new `results/*.json` and the
   README table. CI validates every result against `schema.json` and re-renders the
   table, so a hand-edited row fails the build.

## Rules that keep rows comparable

- The JSON is the source of truth. Never type a table row by hand.
- Keep `prompt_id` exactly as the tool produced it. A run from a different prompt is
  not comparable to the rest of the table and will be rejected.
- `unknown` is a valid value. Leave it where the tool wrote it instead of filling it
  in from memory.
- A run with `status` other than `ok` is still welcome, but it is evidence that the
  model failed there, not a speed measurement. It goes in the table as that.
- One pull request per machine. Measuring six models on the same box is fine in a
  single pull request; mixing results from several machines is not.

## What I need in the pull request description

The numbers in the JSON cover the hardware, so keep this short:

- whether the machine has a dedicated GPU, and whether Ollama was using it
- anything unusual about the run, such as a thermal limit, a battery saver profile,
  or other heavy programs open at the time

## Code changes

Open an issue first if the change touches `PROMPT`, `PROMPT_ID`, `schema.json` or the
verdict thresholds. Those four decide whether old rows stay comparable to new ones,
so changing them invalidates the table and needs a migration, not a patch.

Everything else is ordinary: keep the standard library only, add a test next to the
behaviour you changed, and run the suite before pushing.

```sh
python -m unittest -v test_potatollm
```

The tool has no runtime dependencies and that is a hard constraint, not a preference.
It has to run on a machine too weak to install anything.
