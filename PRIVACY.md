# NuffSaid privacy policy

Last updated: 12 October 2026

NuffSaid has no account, no analytics and no tracking. Here is everything it does with your data.

## Your voice
- NuffSaid records only while you hold Ctrl+Win (or after you double-tap for hands-free) and stops when you let go.
- Your voice is turned into text **on your PC**. Audio is never saved and never sent anywhere.

## Your text
- The last 200 dictations and your personal dictionary are saved **on your PC** (in `%LOCALAPPDATA%\DictationApp`). Clear history in the app, or delete that folder.
- **Auto cleanup** is optional. If you run it on your PC (Ollama), your text stays on your PC. If you choose an online provider (for example OpenRouter, OpenAI or Groq) and add your own key, your dictated text (never audio) is sent to that provider to be cleaned up, under that provider's privacy policy. Your key is stored on your PC, encrypted for your Windows account.

## Network connections NuffSaid makes
1. **First-run setup**, only when you press Start: downloads the speech model from Hugging Face (huggingface.co) and, on PCs with an NVIDIA card, NVIDIA's official packages from PyPI (pypi.org, files.pythonhosted.org). These are ordinary downloads; those servers see a standard web request.
2. **Update check**, once a day: asks GitHub (api.github.com) for the latest version number. It sends nothing about you. Turn it off in the installer or in Settings → Check for updates.
3. **Online cleanup**, only if you set it up (see above).

Nothing else leaves your PC. The "Follow" button only opens Instagram in your browser when you click it.

## The website
nuffsaid.pages.dev asks for your email before you download. It is stored on Cloudflare and used only to tell you about NuffSaid updates. It is never sold or shared. To be removed, open an issue at github.com/sachikaindra/nuffsaid or message @nuffsaid.app on Instagram.

## Questions
Open an issue at github.com/sachikaindra/nuffsaid.
