"""Run the same samples as bench_cleanup_models.py through the online provider (OpenRouter by default) with the saved key."""
import logging, sys, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.argv = sys.argv[:1]                      # bench module reads model names from argv; give it none
logging.basicConfig(level=logging.ERROR)
from openrouter_cleanup import cleanup, load_key, MODEL
from cleanup_text import PROMPT
import importlib.util
spec = importlib.util.spec_from_file_location('bench', ROOT / 'tools' / 'bench_cleanup_models.py')
bench = importlib.util.module_from_spec(spec); spec.loader.exec_module(bench)

key = load_key(ROOT / 'dist' / 'NuffSaid' / 'data' / 'openrouter.key.dpapi')
session, times, kept, fillers = requests.Session(), [], 0, 0
for text in bench.SAMPLES:
    t = time.perf_counter()
    try:
        out, _ = cleanup(session, key, text, PROMPT)
    except Exception as exc:
        out = text; print('  error:', exc)
    times.append(time.perf_counter() - t)
    kept += out == text
    fillers += len(bench.FILLERS.findall(out))
    print(f"  [{'ORIGINAL' if out == text else 'cleaned '}] {out[:120]}")
print(f"{MODEL}: avg {sum(times)/len(times):.2f}s  max {max(times):.2f}s  kept-original {kept}/8  fillers left {fillers}")
