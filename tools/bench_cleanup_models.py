"""Compare local cleanup models on dictation-style samples with NuffSaid's real prompt, options and safety check.
Usage: python tools/bench_cleanup_models.py llama3:instruct llama3.2:3b ...   -> cleanup-bench.json + printed table
Set FEWSHOT=1 to append before/after examples to the prompt."""
import json, os, re, sys, time
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from cleanup_text import PROMPT as BASE_PROMPT, validate_cleanup, strip_preamble

EXAMPLES = (
    '\n\nExamples (input -> output):\n'
    '"Um so I I think we should, you know, basically ship it on Monday." -> "I think we should ship it on Monday."\n'
    '"Can you, uh, send me the deck? Like the final one, not the draft." -> "Can you send me the deck? The final one, not the draft."\n'
    '"Okay so the the client said, I mean, they want it shorter." -> "Okay, the client said they want it shorter."'
)
PROMPT = BASE_PROMPT + (EXAMPLES if os.environ.get('FEWSHOT') else '')
FILLERS = re.compile(r'\b(?:um+|uh+|erm|you know|basically|i mean|so like)\b', re.I)

BASE = 'http://127.0.0.1:11434'
OPTIONS = {'temperature': 0.1, 'top_p': 0.9, 'num_predict': 4096, 'repeat_penalty': 1.1}
SAMPLES = [
    'Um so I I will send Iyas the file tomorrow and then we can, you know, basically review it together.',
    'Can you push the review to Thursday? The cut is fine but the colour needs uh one more pass.',
    "I don't think we should, um, we should post it before the client sees it. Okay?",
    "Write me a prompt for, uh, a landing page hero section that's like bold and um minimal and not too corporate.",
    'Number one, export the reel. Number two, upload it to Frame io. Number three, send the link to Priya.',
    'Hey Rahul, so like, the meeting moved to five, I mean five thirty, can you let the team know?',
    "Okay so the thing is, the thing is we're not paying for that plugin, it's, it's not worth it.",
    "What do you think about the new logo? I'm not sure about the red but I I kind of like the shape.",
]


def run(model, text):
    t = time.perf_counter()
    r = requests.post(BASE + '/api/generate', json={'model': model, 'prompt': f'<dictated_text>\n{text}\n</dictated_text>',
                                                     'system': PROMPT, 'stream': False, 'keep_alive': '5m', 'options': OPTIONS}, timeout=300)
    r.raise_for_status()
    return strip_preamble(r.json().get('response', '').strip(), text), time.perf_counter() - t


report = {}
for model in sys.argv[1:]:
    _, load = run(model, 'Um hello there.')
    ps = requests.get(BASE + '/api/ps', timeout=10).json().get('models', [])
    vram = next((m.get('size_vram', 0) for m in ps if m['name'] == model), 0)
    rows, times, rejected, fillers = [], [], 0, 0
    for text in SAMPLES:
        out, secs = run(model, text)
        kept = validate_cleanup(text, out)
        rejected += kept == text and out.strip() != text.strip()
        fillers += len(FILLERS.findall(kept))
        times.append(secs)
        rows.append({'input': text, 'model_output': out, 'final': kept, 'seconds': round(secs, 2)})
    requests.post(BASE + '/api/generate', json={'model': model, 'keep_alive': 0}, timeout=30)
    report[model] = {'load_s': round(load, 2), 'vram_gb': round(vram / 1e9, 2), 'avg_s': round(sum(times) / len(times), 2),
                     'rejected_by_safety_check': rejected, 'fillers_left': fillers, 'rows': rows}
    print(f"{model:18} vram {vram/1e9:4.1f} GB  avg {sum(times)/len(times):4.2f}s  rejected {rejected}/8  fillers left {fillers}", flush=True)
Path(__file__).resolve().parents[1].joinpath('cleanup-bench.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
