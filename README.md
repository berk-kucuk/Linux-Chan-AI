# Linux Chan AI — Anime Girl Desktop Assistant

**Linux Chan** is an anime-style AI desktop assistant built with PyQt5 and powered by Google Gemini. She runs natively on Linux, supports voice output, can execute shell commands, and comes with a polished glass-style UI with animated character artwork.

---

## Features

### AI & Agents
- **Multi-agent system** — automatically routes your message to the right agent:
  - `friend_chat` — casual conversation and general questions
  - `linux_command` — generates and runs shell commands with explained output
  - `weather_gether` — fetches live weather data
- **Automatic model fallback** — if a Gemini model hits its rate limit (429), Linux Chan silently switches to the next available model and continues without interruption
- **File attachment** — attach `.txt`, `.py`, `.sh`, `.json`, `.yaml`, `.log`, and many other text/code formats to include in your prompt

### UI & Design
- **Glass theme** (default) — deep dark background with indigo/blue aurora gradient, frosted-glass cards, and semi-transparent bars
- **6 additional themes** — Midnight Blue, Dark Rose, Light, Cyberpunk, Purple Haze, Sakura
- **Two layout modes**:
  - `Vertical` — character portrait banner on top, chat below
  - `Wide` — full-body character sidebar on the left, chat on the right
- **Depth blur effect** — character artwork is rendered with a double-layer pre-baked Gaussian blur halo (super-halo + mid-halo) for a cinematic depth feel
- **Direct shell commands** — prefix any message with `!` to run it as a raw shell command (e.g. `! df -h`)

### Voice
- **Text-to-speech** via gTTS + pygame — toggle on/off from the top bar
- Supports all 6 UI languages: English, Turkish, Spanish, German, French, Russian

---

## Requirements

- Python 3.10+
- NixOS / Nix (optional, `shell.nix` provided) or manual pip install
- A [Google Gemini API key](https://aistudio.google.com/)
- Optional: [WeatherAPI key](https://www.weatherapi.com/) for weather queries

---

## Installation

### With Nix

```bash
git clone https://github.com/berkucuk/Linux-Chan-AI.git
cd Linux-Chan-AI
nix-shell
python main.py
```

### Without Nix

```bash
git clone https://github.com/berkucuk/Linux-Chan-AI.git
cd Linux-Chan-AI
pip install -r requirements.txt
python main.py
```

---

## Setup

1. Launch the app — it opens on the **Chat** tab
2. Go to **Settings**
3. Enter your **Gemini API key** (required)
4. Optionally enter a **WeatherAPI key**
5. Choose a **Gemini model** — default is `gemini-2.5-flash-lite`
6. Click **Save & Connect**

Settings are stored in a local `.env` file.

---

## Gemini Models

| Model | Notes |
|---|---|
| `gemini-2.5-flash-lite` | Default — fastest, lowest quota usage |
| `gemini-2.5-flash` | Smarter, slightly heavier |
| `gemini-2.0-flash` | Previous generation |
| `gemini-2.0-flash-lite` | Previous generation lite |
| `gemini-3.1-flash-lite-preview` | Preview |
| `gemini-3-flash-preview` | Preview |
| `gemini-flash-latest` | Always latest flash |
| `gemini-flash-lite-latest` | Always latest flash lite |

If the active model is rate-limited, Linux Chan automatically falls back through the list.

---

## Supported Languages

| Language | Code |
|---|---|
| English | `en` |
| Turkish | `tr` |
| Spanish | `es` |
| German | `de` |
| French | `fr` |
| Russian | `ru` |

---

## License

Distributed under the MIT License. See `LICENSE` for details.
