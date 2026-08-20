#!/usr/bin/env python3
"""potatollm: CPU/RAM-focused Ollama benchmark helper."""

import argparse
import ctypes
import datetime as _dt
import glob
import json
import math
import os
import platform
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

SCHEMA_VERSION = "2.0"
PROMPT_ID = "lowrambench-v1-fixed-120"  # must stay unchanged: identifies fixed prompt; changing would invalidate comparison with existing results/
PROMPT = (
    "Write a concise practical checklist for deciding whether a local language "
    "model is usable on a low-RAM CPU-only computer. Use plain English and keep "
    "the answer under 120 words."
)
OLLAMA_URL = "http://127.0.0.1:11434"
RESULTS_DIR = Path(__file__).resolve().parent / "results"
UNKNOWN = "unknown"

VERDICTS = ["fits comfortably", "tight fit", "will page", "do not try"]


class PotatoLLMError(Exception):
    pass


class ThrashingAbort(PotatoLLMError):
    pass


def now_iso():
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def safe_float(value):
    try:
        if value is None or value == UNKNOWN:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def bytes_to_gb(value):
    if value is None or value == UNKNOWN:
        return UNKNOWN
    try:
        return round(float(value) / (1024 ** 3), 3)
    except (TypeError, ValueError):
        return UNKNOWN


def gb_to_bytes(value):
    try:
        return int(float(value) * (1024 ** 3))
    except (TypeError, ValueError):
        return None


def human_gb(value):
    number = safe_float(value)
    if number is None:
        return UNKNOWN
    return f"{number:.2f} GB"


def get_windows_memory():
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    stat = MEMORYSTATUSEX()
    stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
        raise OSError("GlobalMemoryStatusEx failed")
    pagefile_used = max(0, int(stat.ullTotalPageFile) - int(stat.ullAvailPageFile))
    return {
        "ram_total_gb": bytes_to_gb(stat.ullTotalPhys),
        "ram_free_gb": bytes_to_gb(stat.ullAvailPhys),
        "pagefile_total_gb": bytes_to_gb(stat.ullTotalPageFile),
        "pagefile_free_gb": bytes_to_gb(stat.ullAvailPageFile),
        "pagefile_used_gb": bytes_to_gb(pagefile_used),
    }


def read_proc_meminfo():
    info = {}
    with open("/proc/meminfo", "r", encoding="utf-8") as handle:
        for line in handle:
            parts = line.split()
            if len(parts) >= 2:
                key = parts[0].rstrip(":")
                try:
                    info[key] = int(parts[1]) * 1024
                except ValueError:
                    pass
    total = info.get("MemTotal")
    available = info.get("MemAvailable", info.get("MemFree"))
    swap_total = info.get("SwapTotal")
    swap_free = info.get("SwapFree")
    swap_used = None
    if swap_total is not None and swap_free is not None:
        swap_used = max(0, swap_total - swap_free)
    return {
        "ram_total_gb": bytes_to_gb(total),
        "ram_free_gb": bytes_to_gb(available),
        "pagefile_total_gb": bytes_to_gb(swap_total),
        "pagefile_free_gb": bytes_to_gb(swap_free),
        "pagefile_used_gb": bytes_to_gb(swap_used),
    }


def get_memory_snapshot():
    system = platform.system().lower()
    try:
        if system == "windows":
            return get_windows_memory()
        if os.path.exists("/proc/meminfo"):
            return read_proc_meminfo()
    except Exception:
        pass
    return {
        "ram_total_gb": UNKNOWN,
        "ram_free_gb": UNKNOWN,
        "pagefile_total_gb": UNKNOWN,
        "pagefile_free_gb": UNKNOWN,
        "pagefile_used_gb": UNKNOWN,
    }


def get_cpu_name():
    cpu = platform.processor() or platform.machine()
    return cpu if cpu else UNKNOWN


def get_os_name():
    text = platform.platform(aliased=True)
    return text if text else UNKNOWN


def http_json(method, url, payload=None, timeout=8):
    data = None
    headers = {"User-Agent": "potatollm/1.0"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        raise PotatoLLMError(f"HTTP {exc.code} from {url}: {detail}")
    except urllib.error.URLError as exc:
        raise PotatoLLMError(f"Cannot reach {url}: {exc.reason}")
    except TimeoutError:
        raise PotatoLLMError(f"Timeout reaching {url}")
    except json.JSONDecodeError as exc:
        raise PotatoLLMError(f"Invalid JSON from {url}: {exc}")


def http_text(url, timeout=10):
    req = urllib.request.Request(url, headers={"User-Agent": "potatollm/1.0"}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        raise PotatoLLMError(f"HTTP {exc.code} from {url}")
    except urllib.error.URLError as exc:
        raise PotatoLLMError(f"Cannot reach {url}: {exc.reason}")
    except TimeoutError:
        raise PotatoLLMError(f"Timeout reaching {url}")


def split_model(model):
    if ":" in model:
        name, tag = model.split(":", 1)
        return name.strip(), tag.strip() or "latest"
    return model.strip(), "latest"


def model_match(candidate, requested):
    c = str(candidate).lower()
    r = requested.lower()
    if c == r:
        return True
    if ":" not in r and (c == r + ":latest" or c.startswith(r + ":")):
        return True
    return False


def get_local_model_info(model):
    tags = http_json("GET", OLLAMA_URL + "/api/tags", timeout=2)
    models = tags.get("models", []) if isinstance(tags, dict) else []
    for item in models:
        names = [item.get("name"), item.get("model")]
        if any(name and model_match(name, model) for name in names):
            details = item.get("details") or {}
            return {
                "source": "local Ollama",
                "backend": "ollama",
                "backend_version": get_ollama_version(default=UNKNOWN),
                "size_gb": bytes_to_gb(item.get("size")),
                "quantization": details.get("quantization_level") or UNKNOWN,
                "exact_model": item.get("name") or item.get("model") or model,
            }
    raise PotatoLLMError(f"Model '{model}' was not found in local Ollama tags")


def parse_size_to_gb(text):
    if not text:
        return UNKNOWN
    matches = re.findall(r"(\d+(?:\.\d+)?)\s*(GB|MB|GiB|MiB)\b", text, flags=re.I)
    values = []
    for number, unit in matches:
        n = float(number)
        unit = unit.lower()
        if unit in ("mb", "mib"):
            n = n / 1024.0
        values.append(n)
    if not values:
        return UNKNOWN
    # Prefer plausible model artifact sizes over page boilerplate numbers.
    plausible = [v for v in values if 0.05 <= v <= 500]
    if plausible:
        return round(max(plausible), 3)
    return round(max(values), 3)


def parse_quantization(text, model):
    candidates = []
    for source in [model, text[:200000] if text else ""]:
        candidates.extend(re.findall(r"\b(Q[234568](?:_[A-Z0-9_]+)?|F16|BF16|FP16|FP32)\b", source, flags=re.I))
    if candidates:
        return candidates[0].upper()
    return UNKNOWN


def get_public_model_info(model):
    name, tag = split_model(model)
    path = name
    if tag and tag != "latest":
        path = f"{name}:{tag}"
    if "/" in name:
        url = "https://ollama.com/" + urllib.parse.quote(path, safe=":/-")
    else:
        url = "https://ollama.com/library/" + urllib.parse.quote(path, safe=":/-")
    text = http_text(url, timeout=10)
    if "404" in text[:1000].lower() and "not found" in text[:5000].lower():
        raise PotatoLLMError(f"Model '{model}' was not found on ollama.com")
    return {
        "source": "ollama.com",
        "backend": "ollama",
        "backend_version": UNKNOWN,
        "size_gb": parse_size_to_gb(text),
        "quantization": parse_quantization(text, model),
        "exact_model": model,
    }


def get_model_info_for_check(model):
    try:
        return get_local_model_info(model)
    except PotatoLLMError as local_error:
        try:
            info = get_public_model_info(model)
            info["local_note"] = str(local_error)
            return info
        except PotatoLLMError as public_error:
            raise PotatoLLMError(
                f"Could not read model metadata locally or from ollama.com. Local: {local_error}. Public: {public_error}"
            )


def get_ollama_version(default=None):
    try:
        data = http_json("GET", OLLAMA_URL + "/api/version", timeout=2)
        return data.get("version") or default or UNKNOWN
    except PotatoLLMError:
        return default if default is not None else UNKNOWN


def classify_fit(ram_total_gb, ram_free_gb, model_size_gb):
    total = safe_float(ram_total_gb)
    size = safe_float(model_size_gb)
    if total is None or size is None or total <= 0:
        return UNKNOWN
    ratio = size / total
    if ratio <= 0.22:
        return "fits comfortably"
    if ratio <= 0.35:
        return "tight fit"
    if ratio <= 0.50:
        return "will page"
    return "do not try"


def ram_free_warning(ram_free_gb, model_size_gb):
    free = safe_float(ram_free_gb)
    size = safe_float(model_size_gb)
    if free is None:
        return None
    threshold = 1.0
    if size is not None:
        threshold = max(threshold, min(2.5, size * 0.75 + 0.5))
    if free < threshold:
        return f"RAM free now: {human_gb(free)} — close programs before running"
    return None


def get_local_model_names():
    tags = http_json("GET", OLLAMA_URL + "/api/tags", timeout=2)
    models = tags.get("models", []) if isinstance(tags, dict) else []
    names = []
    for item in models:
        for key in ("name", "model"):
            value = item.get(key)
            if value and value not in names:
                names.append(value)
    return names


def suggest_smaller(model, verdict):
    if verdict not in ("will page", "do not try"):
        return "none"
    patterns = [(r"14b", "8b"), (r"13b", "7b"), (r"8b", "4b"), (r"7b", "3b"), (r"4b", "3b"), (r"3b", "1.5b")]
    candidates = []
    for old, new in patterns:
        if re.search(old, model, flags=re.I):
            candidates.append(re.sub(old, new, model, flags=re.I))
    try:
        local_names = get_local_model_names()
    except PotatoLLMError:
        local_names = []
    for candidate in candidates:
        if any(model_match(name, candidate) for name in local_names):
            return candidate
    return "try a 3B or smaller quantized model"


def cmd_check(args):
    try:
        mem = get_memory_snapshot()
        info = get_model_info_for_check(args.model)
        verdict = classify_fit(mem["ram_total_gb"], mem["ram_free_gb"], info["size_gb"])
        print(f"Model: {info.get('exact_model', args.model)}")
        print(f"Metadata source: {info.get('source', UNKNOWN)}")
        if info.get("local_note"):
            print(f"Local Ollama: {info['local_note']}")
        print(f"Size: {human_gb(info.get('size_gb'))}")
        print(f"Quantization: {info.get('quantization', UNKNOWN)}")
        print(f"RAM total: {human_gb(mem.get('ram_total_gb'))}")
        warning = ram_free_warning(mem.get("ram_free_gb"), info.get("size_gb"))
        if warning:
            print(warning)
        print(f"Verdict by total RAM: {verdict}")
        if verdict in ("will page", "do not try"):
            print(f"Smaller alternative: {suggest_smaller(args.model, verdict)}")
        if verdict == UNKNOWN:
            return 2
        return 0
    except PotatoLLMError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


class Sampler:
    def __init__(self, interval=0.25):
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.samples = []
        self.min_ram_free = None
        self.max_pagefile_used = None
        self.low_ram_since = None
        self.thrash_snapshot = None

    def start(self):
        self._sample()
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.thread.join(timeout=2)
        self._sample()

    def _run(self):
        while not self.stop_event.wait(self.interval):
            self._sample()

    def _sample(self):
        snap = get_memory_snapshot()
        now = time.time()
        self.samples.append((now, snap))
        ram_free = safe_float(snap.get("ram_free_gb"))
        pagefile_used = safe_float(snap.get("pagefile_used_gb"))
        if ram_free is not None:
            self.min_ram_free = ram_free if self.min_ram_free is None else min(self.min_ram_free, ram_free)
            if ram_free < 0.15:
                if self.low_ram_since is None:
                    self.low_ram_since = now
                self.thrash_snapshot = snap
            else:
                self.low_ram_since = None
                self.thrash_snapshot = None
        if pagefile_used is not None:
            self.max_pagefile_used = pagefile_used if self.max_pagefile_used is None else max(self.max_pagefile_used, pagefile_used)

    def thrashing_for(self):
        if self.low_ram_since is None:
            return 0.0
        return max(0.0, time.time() - self.low_ram_since)


def detect_paging(before, sampler, after):
    before_pf = safe_float(before.get("pagefile_used_gb"))
    peak_pf = sampler.max_pagefile_used
    min_ram = sampler.min_ram_free
    if before_pf is None or peak_pf is None:
        return UNKNOWN
    if peak_pf > before_pf + 0.25:
        return True
    if min_ram is not None and min_ram < 0.2:
        return True
    return False


def build_result(model, model_info, before, sampler, after, response, elapsed_seconds, status="completed"):
    eval_count = response.get("eval_count")
    eval_duration_ns = response.get("eval_duration")
    tok_s = UNKNOWN
    duration_s = round(elapsed_seconds, 3)
    if isinstance(eval_count, (int, float)) and isinstance(eval_duration_ns, (int, float)) and eval_duration_ns > 0:
        tok_s = round(float(eval_count) / (float(eval_duration_ns) / 1_000_000_000.0), 3)
        duration_s = round(float(eval_duration_ns) / 1_000_000_000.0, 3)
    return {
        "schema_version": SCHEMA_VERSION,
        "date": now_iso(),
        "model": model,
        "quantization": model_info.get("quantization", UNKNOWN),
        "size_gb": model_info.get("size_gb", UNKNOWN),
        "backend": "ollama",
        "backend_version": get_ollama_version(default=UNKNOWN),
        "cpu": get_cpu_name(),
        "ram_total_gb": before.get("ram_total_gb", UNKNOWN),
        "os": get_os_name(),
        "prompt_id": PROMPT_ID,
        "generated_tokens": eval_count if eval_count is not None else UNKNOWN,
        "duration_s": duration_s,
        "tok_s": tok_s,
        "min_free_ram_gb": round(sampler.min_ram_free, 3) if sampler.min_ram_free is not None else UNKNOWN,
        "peak_pagefile_gb": round(sampler.max_pagefile_used, 3) if sampler.max_pagefile_used is not None else UNKNOWN,
        "paged": detect_paging(before, sampler, after),
        "status": status,
    }


def build_aborted_result(model, model_info, before, sampler, after, elapsed_seconds):
    return {
        "schema_version": SCHEMA_VERSION,
        "date": now_iso(),
        "model": model,
        "quantization": model_info.get("quantization", UNKNOWN),
        "size_gb": model_info.get("size_gb", UNKNOWN),
        "backend": "ollama",
        "backend_version": get_ollama_version(default=UNKNOWN),
        "cpu": get_cpu_name(),
        "ram_total_gb": before.get("ram_total_gb", UNKNOWN),
        "os": get_os_name(),
        "prompt_id": PROMPT_ID,
        "generated_tokens": UNKNOWN,
        "duration_s": round(elapsed_seconds, 3),
        "tok_s": UNKNOWN,
        "min_free_ram_gb": round(sampler.min_ram_free, 3) if sampler.min_ram_free is not None else UNKNOWN,
        "peak_pagefile_gb": round(sampler.max_pagefile_used, 3) if sampler.max_pagefile_used is not None else UNKNOWN,
        "paged": True,
        "status": "aborted: thrashing detected",
    }


def post_generate_with_abort(payload, timeout, sampler):
    box = {}

    def worker():
        try:
            box["response"] = http_json("POST", OLLAMA_URL + "/api/generate", payload=payload, timeout=timeout)
        except Exception as exc:
            box["error"] = exc

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    started = time.monotonic()
    while thread.is_alive():
        if sampler.thrashing_for() > 20.0:
            raise ThrashingAbort("aborted: thrashing detected")
        if time.monotonic() - started > timeout:
            raise PotatoLLMError(f"Timeout reaching {OLLAMA_URL}/api/generate")
        time.sleep(0.25)
    if "error" in box:
        raise box["error"]
    return box.get("response")


def result_filename(model):
    stamp = _dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", model).strip("_") or "model"
    return RESULTS_DIR / f"{stamp}-{safe}.json"


def write_result(result, path=None):
    RESULTS_DIR.mkdir(exist_ok=True)
    out = Path(path) if path else result_filename(str(result.get("model", result.get("modelo", "model"))))
    with open(out, "w", encoding="utf-8") as handle:
        json.dump(result, handle, indent=2, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
    return out


def cmd_bench(args):
    try:
        try:
            model_info = get_local_model_info(args.model)
        except PotatoLLMError:
            model_info = {"quantization": UNKNOWN, "size_gb": UNKNOWN}
        before = get_memory_snapshot()
        sampler = Sampler()
        payload = {"model": args.model, "prompt": PROMPT, "stream": False, "options": {"num_predict": 120}}
        sampler.start()
        start = time.perf_counter()
        aborted = False
        try:
            response = post_generate_with_abort(payload, args.timeout, sampler)
        except ThrashingAbort:
            aborted = True
            response = None
        finally:
            elapsed = time.perf_counter() - start
            sampler.stop()
        after = get_memory_snapshot()
        if aborted:
            result = build_aborted_result(args.model, model_info, before, sampler, after, elapsed)
            path = write_result(result)
            print(f"Wrote: {path}")
            print("aborted: thrashing detected")
            print(f"Min free RAM: {human_gb(result['min_free_ram_gb'])}; peak pagefile: {human_gb(result['peak_pagefile_gb'])}")
            print(format_table([result]))
            return 2
        if not isinstance(response, dict) or response.get("error"):
            raise PotatoLLMError(str(response.get("error", "Unexpected Ollama response")))
        result = build_result(args.model, model_info, before, sampler, after, response, elapsed)
        path = write_result(result)
        print(f"Wrote: {path}")
        print(format_table([result]))
        return 0
    except PotatoLLMError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        print("Make sure Ollama is running and the model exists locally. This command never pulls models.", file=sys.stderr)
        return 2


def sample_result():
    mem = get_memory_snapshot()
    return {
        "schema_version": SCHEMA_VERSION,
        "date": now_iso(),
        "model": "selftest-example",
        "quantization": UNKNOWN,
        "size_gb": UNKNOWN,
        "backend": "ollama",
        "backend_version": get_ollama_version(default=UNKNOWN),
        "cpu": get_cpu_name(),
        "ram_total_gb": mem.get("ram_total_gb", UNKNOWN),
        "os": get_os_name(),
        "prompt_id": PROMPT_ID,
        "generated_tokens": 0,
        "duration_s": 0,
        "tok_s": 0,
        "min_free_ram_gb": mem.get("ram_free_gb", UNKNOWN),
        "peak_pagefile_gb": mem.get("pagefile_used_gb", UNKNOWN),
        "paged": False,
        "status": "completed",
    }


def row_value(value):
    if value is True:
        return "yes"
    if value is False:
        return "no"
    if value is None:
        return UNKNOWN
    return str(value)


def normalize_result(data):
    if not isinstance(data, dict):
        return None
    if data.get("schema_version") == SCHEMA_VERSION:
        return data
    if data.get("schema_version") == "1.0":
        return {
            "schema_version": SCHEMA_VERSION,
            "date": data.get("data", UNKNOWN),
            "model": data.get("modelo", UNKNOWN),
            "quantization": data.get("quantizacao", UNKNOWN),
            "size_gb": data.get("tamanho", UNKNOWN),
            "backend": data.get("backend", UNKNOWN),
            "backend_version": data.get("versao_do_backend", UNKNOWN),
            "cpu": data.get("CPU", UNKNOWN),
            "ram_total_gb": data.get("RAM_total", UNKNOWN),
            "os": data.get("OS", UNKNOWN),
            "prompt_id": data.get("prompt_id", UNKNOWN),
            "generated_tokens": data.get("tokens_gerados", UNKNOWN),
            "duration_s": data.get("duracao", UNKNOWN),
            "tok_s": data.get("tok_s", UNKNOWN),
            "min_free_ram_gb": data.get("RAM_livre_no_pico", UNKNOWN),
            "peak_pagefile_gb": data.get("pagefile_no_pico", UNKNOWN),
            "paged": data.get("paginou", UNKNOWN),
            "status": "completed",
        }
    return None


def format_table(results):
    headers = ["date", "model", "quant", "size GB", "RAM GB", "tokens", "seconds", "tok/s", "min free RAM GB", "peak pagefile GB", "paged"]
    rows = []
    for r in results:
        if r.get("model") == "selftest-example":
            continue
        rows.append([
            str(r.get("date", UNKNOWN))[:10],
            r.get("model", UNKNOWN),
            r.get("quantization", UNKNOWN),
            row_value(r.get("size_gb", UNKNOWN)),
            row_value(r.get("ram_total_gb", UNKNOWN)),
            row_value(r.get("generated_tokens", UNKNOWN)),
            row_value(r.get("duration_s", UNKNOWN)),
            row_value(r.get("tok_s", UNKNOWN)),
            row_value(r.get("min_free_ram_gb", UNKNOWN)),
            row_value(r.get("peak_pagefile_gb", UNKNOWN)),
            row_value(r.get("paged", UNKNOWN)),
        ])
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for row in rows:
        lines.append("| " + " | ".join(str(cell).replace("\n", " ") for cell in row) + " |")
    return "\n".join(lines)


def load_result_file(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        normalized = normalize_result(data)
        if normalized:
            return normalized
        print(f"WARNING: skipping {path}: unsupported schema_version", file=sys.stderr)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"WARNING: skipping {path}: {exc}", file=sys.stderr)
    return None


def cmd_table(args):
    paths = sorted(glob.glob(str(RESULTS_DIR / "*.json")))
    results = [r for r in (load_result_file(p) for p in paths) if r]
    if not results:
        print("No result JSON files found in results/.")
        return 1
    print(format_table(results))
    return 0


def selftest_item(name, func):
    try:
        message = func()
        print(f"PASS {name}: {message}")
        return True
    except Exception as exc:
        print(f"FAIL {name}: {exc}")
        return False


def cmd_selftest(args):
    ok = []

    def check_python():
        version = sys.version_info
        if version < (3, 9):
            raise PotatoLLMError(f"Python {version.major}.{version.minor} is too old; need 3.9+")
        return platform.python_version()

    def check_memory():
        mem = get_memory_snapshot()
        if mem.get("ram_total_gb") == UNKNOWN or mem.get("ram_free_gb") == UNKNOWN:
            raise PotatoLLMError("RAM total/free is unknown on this platform")
        if mem.get("pagefile_used_gb") == UNKNOWN:
            raise PotatoLLMError("pagefile/swap usage is unknown on this platform")
        return f"RAM total {human_gb(mem['ram_total_gb'])}, free {human_gb(mem['ram_free_gb'])}, pagefile used {human_gb(mem['pagefile_used_gb'])}"

    def check_ollama():
        data = http_json("GET", OLLAMA_URL + "/api/version", timeout=2)
        if not isinstance(data, dict):
            raise PotatoLLMError("Ollama responded with a non-object version payload")
        version = data.get("version")
        if version:
            return f"Ollama responded, version {version}"
        return "Ollama responded, version unknown"

    def check_json_table():
        result = sample_result()
        path = RESULTS_DIR / "selftest-example.json"
        write_result(result, path=path)
        loaded = load_result_file(path)
        if not loaded:
            raise PotatoLLMError("Could not read back selftest JSON")
        table = format_table([loaded])
        if "selftest-example" in table or "|" not in table:
            raise PotatoLLMError("Selftest JSON was not ignored correctly by public table rendering")
        return f"wrote {path}; selftest rows are ignored by public table"

    ok.append(selftest_item("python", check_python))
    ok.append(selftest_item("memory", check_memory))
    ok.append(selftest_item("ollama", check_ollama))
    ok.append(selftest_item("json_table", check_json_table))
    return 0 if all(ok) else 1


def build_parser():
    parser = argparse.ArgumentParser(description="Benchmark whether Ollama models fit low-RAM CPU-only machines.")
    sub = parser.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser("check", help="RAM verdict without pulling a model")
    p_check.add_argument("model")
    p_check.set_defaults(func=cmd_check)
    p_bench = sub.add_parser("bench", help="Run a real fixed-prompt Ollama benchmark")
    p_bench.add_argument("model")
    p_bench.add_argument("--timeout", type=int, default=300, help="Ollama request timeout in seconds")
    p_bench.set_defaults(func=cmd_bench)
    p_self = sub.add_parser("selftest", help="Diagnose Python, memory, Ollama ping, JSON and table path")
    p_self.set_defaults(func=cmd_selftest)
    p_table = sub.add_parser("table", help="Print Markdown table from results/*.json")
    p_table.set_defaults(func=cmd_table)
    return parser


def main(argv=None):
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except KeyboardInterrupt:
        print("ERROR: interrupted", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
