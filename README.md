# Linux Chan AI — Anime Girl Assistant

<p align="center">
  <img src="icons/horny2.png" width="220" alt="Linux Chan"/>
</p>

**Linux Chan** is a desktop AI assistant with an anime girl personality, powered by **Google Gemini**. She lives in a frameless dark-themed window on your desktop, reacts to conversations with dynamic expressions, helps you with Linux commands, reads and writes files, and keeps you company even when you're away.

---

## Features

- **Google Gemini backend** — 8 models to choose from (default: `gemini-2.5-flash-lite`)
- **Multi-turn chat memory** — remembers the full conversation, up to 40 exchanges
- **9 personalities** — each changes chat style, image mood, and behavior:

  | Personality | Description |
  |---|---|
  | Sweet 💖 | Warm, caring, sisterly — never flirts |
  | Flirty 💋 | Extremely seductive, shameless innuendo at all times |
  | Aggressive 😤 | Foul-mouthed rage machine — insults you constantly but always correct |
  | Tsundere ❄️ | Snappy and dismissive on the surface, helpfulness leaks through anyway |
  | Yandere 🔪 | Dangerously obsessed with you — sweet and threatening in the same breath |
  | Psycho 🤪 | Completely unhinged — correct answers buried in absolute chaos |
  | Professional 💼 | Cold, precise, no anime nonsense whatsoever |
  | Neko 🐱 | Playful cat-girl with a short attention span and lots of nya~ |
  | Genki ✨ | Permanently hyped, relentlessly positive about everything!! |

- **Emotion-based character images** — image changes with smooth fade transitions based on mood:

  | State | Image | When |
  |---|---|---|
  | default / chat | `horny2.png` | Normal replies |
  | thinking | `thoughtful.png` | While generating a response |
  | flirty | `horn1.png` | Flirty/seductive responses (only allowed personalities) |
  | linux | `wild.png` | Running terminal commands |
  | error | `sad.png` | API errors or failures |
  | bored | `bored.png` | Idle notifications |

- **Terminal agent** — asks for approval before running any command, then runs it
  inside a `bwrap` sandbox (falls back to `firejail`; refuses to run if neither is
  installed). The system is readable but read-only, `$HOME` is replaced by an empty
  tmpfs so no dotfile or key is reachable, and `~/Linux-Chan-AI/` is the only
  writable path. `sudo`, `su`, `pkexec` and `doas` are refused.
- **File operations** — read, write, list, delete files inside `~/Linux-Chan-AI/`
- **Voice output** — edge-tts with a female voice per language, streams audio instantly (no temp files)
- **Idle notifications** — sends up to 3 notifications when you're away (30 min, 2 h, 6 h), clickable to reply
- **System alerts** — warns you when CPU >80%, RAM <500 MB free, or temperature >75°C
- **6 languages** — English, Turkish, Spanish, German, French, Russian
- **4 dark themes** — Black, Dark Purple, Dark Blue, Synthwave
- **Horizontal / Vertical layout** — switchable in Settings
- **Frameless window** — custom title bar, draggable, minimizes to system tray on close

---

## Installation

### From the Maze repository

**On Maze Linux** the repository is already configured:

```bash
sudo pacman -S linux-chan-ai
```

**On Arch Linux and Arch-based distributions**, add the repository once:

1. Import and trust the Maze signing key:

   ```bash
   curl -O https://mazerepo.berkkucukk.com.tr/packages/mazelinux.gpg
   gpg --show-keys --with-fingerprint mazelinux.gpg
   sudo pacman-key --add mazelinux.gpg
   sudo pacman-key --lsign-key 7C4D515A6B930CB04794CEF6147C8159B3E2EE5F
   ```

   The fingerprint `gpg` prints must be `7C4D 515A 6B93 0CB0 4794  CEF6 147C 8159 B3E2 EE5F`.

2. Add the repository to the end of `/etc/pacman.conf`:

   ```ini
   [mazelinux]
   SigLevel = Required DatabaseOptional
   Server = https://mazerepo.berkkucukk.com.tr/packages
   ```

3. Sync and install:

   ```bash
   sudo pacman -Syu linux-chan-ai
   ```

Optionally install `mazelinux-keyring` as well; it keeps the signing key up to date through pacman.

Remove with `sudo pacman -Rns linux-chan-ai`.

Then launch it from your application menu or run `linux-chan-ai`.

### Build from source

The package is built from this working tree by `build-pkg.sh` and installed with pacman, exactly like the published one:

```bash
sudo pacman -S --needed base-devel git
git clone https://github.com/berk-kucuk/Linux-Chan-AI.git
cd Linux-Chan-AI
sudo pacman -S --needed $(bash -c 'source packaging/PKGBUILD; echo "${depends[@]}" "${makedepends[@]}"')
./build-pkg.sh --install
```

Without `--install` the package is only built, into `dist-pkg/`.

### Development

Run straight from a checkout in a virtual environment:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 linux-chan.py
```

---

## First Run

On first launch, open **Settings → API Key**, paste your [Google Gemini API key](https://aistudio.google.com/apikey), and hit **Save**. Everything else is configurable from the Settings page.

---

## Configuration

All settings are saved to `~/.config/linux-chan-ai/config.json` automatically.

| Setting | Description |
|---|---|
| Gemini API Key | Your Google AI Studio key |
| Model | Which Gemini model to use |
| Personality | Chat style and image mood of Linux Chan |
| Theme | UI color scheme |
| Language | Response language (also controls TTS voice) |
| Layout | Horizontal (900×560) or Vertical (480×900) |
| Voice | Enable/disable edge-tts voice output |
| Notifications | Enable/disable idle and system alert notifications |

---

## Dependencies

| Package | Purpose |
|---|---|
| `google-genai` | Gemini API |
| `PyQt6` | GUI |
| `edge-tts` | Streaming text-to-speech |
| `python-dotenv` | `.env` support |
| `distro` | Linux distro detection |
| `mpg123` / `ffmpeg` / `mpv` | Audio playback (one required for voice) |

---

## License

Copyright © 2026 Berk Küçük

MIT — see `LICENSE` for details.
