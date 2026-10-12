<p align="center"><img src="assets/nuffsaid.png" width="96" alt="NuffSaid"></p>

# NuffSaid.

**Typing is over.** Hold Ctrl+Win, talk, let go. It types what you said wherever your cursor is. Any app. Free, for Windows.

[Download](https://nuffsaid.pages.dev) · [Instagram](https://instagram.com/nuffsaid.app)

## What it does

| | |
|---|---|
| **Hold Ctrl+Win** | Talk, let go. The text lands where your cursor is. |
| **Double-tap Ctrl+Win** | Hands-free. Ctrl+Win again to stop. |
| **Select text + Win+Alt+E** | Cleans it up. Nothing selected? Cleans your last dictation. |
| **Win+Alt+S** | Pastes the last one again. |
| **Win+Alt+H** | Opens your history. |
| **Esc** | Cancels a recording. |

- **Auto cleanup** (optional): drops ums, stammers and repeats, fixes punctuation. Never rewrites what you meant: a safety check keeps your original words if a cleanup changes meaning. Use our prompt or write your own.
- **Personal dictionary** for the names and words it keeps getting wrong.
- **The blob**: a little red gel that shows up while you talk, moves with your voice, and lives wherever you drag it.

## Where your words go

- Your voice is turned into text **on your PC** (Whisper turbo via faster-whisper). No audio leaves it.
- No account. No sign-up.
- History and your dictionary stay on your PC. Clear them whenever.
- Cleanup runs on your PC through [Ollama](https://ollama.com), or, if you pick it, through an online API with your own key: OpenRouter, OpenAI, Groq or any OpenAI-compatible provider. Then the text (never audio) is sent to that provider. Your key stays on your PC, encrypted for your Windows account.

## What you need

Windows 10 or 11, 64-bit. An NVIDIA graphics card makes it faster; without one it runs on your processor.

## Run from source

```powershell
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python run_flow.py
```

The speech model downloads on first run. For local cleanup, install Ollama and run `ollama pull llama3:instruct`.

## Build

`build-portable.ps1` builds the Windows app with PyInstaller.

## Fonts

The official build uses licensed fonts (Bueno, Aktiv Grotesk) that can't be shared here. Built from source, the app falls back to system fonts. Space Mono is free: put `SpaceMono-Regular.ttf` and `SpaceMono-Bold.ttf` in `assets/fonts/`.

## Licence

[GPL-3.0](LICENSE). Use it, change it, share it. Keep it open.

Made by Sachin. Nuff said.
