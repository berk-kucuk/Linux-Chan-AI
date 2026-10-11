import os
import sys
import re
import json
import shutil
import xml.etree.ElementTree as ET
import subprocess as sub
import logging
import time
from typing import Optional, Tuple

from dotenv import load_dotenv
from google import genai as _genai
import asyncio
import edge_tts

from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox,
    QTextEdit, QLineEdit, QPushButton, QFrame,
    QScrollArea, QStackedWidget, QSystemTrayIcon, QMenu, QMessageBox,
)
from PyQt6.QtGui import (
    QPixmap, QIcon, QPainter, QPainterPath, QPen, QColor, QFont,
    QLinearGradient, QRadialGradient, QBrush, QAction,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QRectF, QPointF, QObject, QTimer

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────

CONFIG_DIR   = os.path.expanduser("~/.config/linux-chan-ai")
CONFIG_PATH  = os.path.join(CONFIG_DIR, "config.json")
ICONS_DIR    = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
SANDBOX_DIR       = os.path.expanduser("~/Linux-Chan-AI")
NOTIF_SCHEDULE    = [30 * 60, 2 * 3600, 6 * 3600]  # 30 min, 2 h, 6 h
SYS_ALERT_COOLDOWN = 30 * 60  # min gap between system alerts


def _icon_path(f: str) -> str:
    for p in [
        f"/usr/share/Linux-Chan-AI/icons/{f}",
        os.path.join(ICONS_DIR, f),
    ]:
        if os.path.exists(p):
            return p
    return ""


# ── State → image mapping ──────────────────────────────────────────────────────

STATE_IMAGES = {
    "default":  "horny2.png",
    "thinking": "thoughtful.png",
    "linux":    "wild.png",
    "chat":     "horny2.png",
    "flirty":   "horn1.png",
    "error":    "sad.png",
    "bored":    "bored.png",
}

_px_cache: dict[str, QPixmap] = {}


def load_state_px(state: str) -> Optional[QPixmap]:
    fname = STATE_IMAGES.get(state, STATE_IMAGES["default"])
    if fname in _px_cache:
        return _px_cache[fname]
    p = _icon_path(fname)
    if not p:
        p = _icon_path(STATE_IMAGES["default"])
    if not p:
        return None
    px = QPixmap(p)
    if px.isNull():
        return None
    _px_cache[fname] = px
    return px


# ── Config ─────────────────────────────────────────────────────────────────────

class Config:
    DEFAULTS = {
        "gemini_api_key": "",
        "gemini_model":   "gemini-2.5-flash",
        "personality":    "Sweet 💖",
        "theme":          "Black",
        "language":       "English",
        "voice":          False,
        "layout":         "horizontal",
        "notifications":  True,
        # Set once the user has seen the notice about where their words go.
        "cloud_notice_ack": False,
    }

    def __init__(self):
        self.data = dict(self.DEFAULTS)
        load_dotenv()
        if os.getenv("GEMINI_API_KEY"):
            self.data["gemini_api_key"] = os.getenv("GEMINI_API_KEY")
        os.makedirs(CONFIG_DIR, exist_ok=True)
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH) as f:
                    for k, v in json.load(f).items():
                        if v not in ("", None):
                            self.data[k] = v
            except Exception:
                pass

    def save(self):
        os.makedirs(CONFIG_DIR, mode=0o700, exist_ok=True)
        # The config holds the Gemini API key: create it 0600 (a plain
        # open("w") gives 0644 under the usual umask) and tighten a file an
        # older version already wrote.
        fd = os.open(CONFIG_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            os.fchmod(fd, 0o600)
        except OSError:
            pass
        with os.fdopen(fd, "w") as f:
            json.dump(self.data, f, indent=2)

    def get(self, k: str):
        return self.data.get(k, self.DEFAULTS.get(k, ""))

    def set(self, k: str, v):
        self.data[k] = v


cfg = Config()

# ── Theme Manager ──────────────────────────────────────────────────────────────

THEMES = {
    "Black": dict(
        bg1="#000000", bg2="#0a0a0a",
        title="#050505", title_border="rgba(255,255,255,18)",
        accent="#e0e0e0", accent2="#999999",
        border="rgba(255,255,255,18)",
        text="#f0f0f0", dim="#606060",
        input_bg="#0c0c0c", chat_bg="#040404",
        btn1="#1a1a1a", btn2="#303030",
        bh1="#282828", bh2="#3e3e3e",
        sect="#101010", sect_b="rgba(80,80,80,80)",
        scroll="#444444", combo="#0e0e0e",
        nav_on="rgba(60,60,60,200)",
        msg="#cccccc",
        glow=(220, 180, 255),
    ),
    "Dark Purple": dict(
        bg1="#0d0b1e", bg2="#080c20",
        title="rgba(8,6,22,240)", title_border="rgba(124,58,237,70)",
        accent="#7c3aed", accent2="#4f46e5",
        border="rgba(124,58,237,70)",
        text="#e2e8f0", dim="#94a3b8",
        input_bg="rgba(18,14,44,220)", chat_bg="rgba(6,4,18,220)",
        btn1="#7c3aed", btn2="#4f46e5",
        bh1="#6d28d9", bh2="#4338ca",
        sect="rgba(14,10,36,200)", sect_b="rgba(124,58,237,60)",
        scroll="#7c3aed", combo="rgba(20,16,50,220)",
        nav_on="rgba(124,58,237,120)",
        msg="#a78bfa",
        glow=(124, 58, 237),
    ),
    "Dark Blue": dict(
        bg1="#080e1e", bg2="#050a16",
        title="rgba(5,8,18,240)", title_border="rgba(59,130,246,70)",
        accent="#3b82f6", accent2="#1d4ed8",
        border="rgba(59,130,246,70)",
        text="#e2e8f0", dim="#94a3b8",
        input_bg="rgba(8,14,28,220)", chat_bg="rgba(4,8,18,220)",
        btn1="#2563eb", btn2="#1d4ed8",
        bh1="#1d4ed8", bh2="#1e40af",
        sect="rgba(8,12,28,200)", sect_b="rgba(59,130,246,60)",
        scroll="#3b82f6", combo="rgba(10,16,32,220)",
        nav_on="rgba(59,130,246,120)",
        msg="#60a5fa",
        glow=(59, 130, 246),
    ),
    "Synthwave": dict(
        bg1="#0c0120", bg2="#16042e",
        title="rgba(8,1,20,240)", title_border="rgba(247,37,133,70)",
        accent="#f72585", accent2="#7209b7",
        border="rgba(247,37,133,70)",
        text="#f0d8ff", dim="#b07aff",
        input_bg="rgba(14,2,42,220)", chat_bg="rgba(6,1,18,220)",
        btn1="#f72585", btn2="#7209b7",
        bh1="#d91e74", bh2="#5c07a0",
        sect="rgba(14,2,40,200)", sect_b="rgba(247,37,133,60)",
        scroll="#f72585", combo="rgba(16,3,48,220)",
        nav_on="rgba(247,37,133,120)",
        msg="#ff79c6",
        glow=(247, 37, 133),
    ),
}

THEME_SWATCHES = {
    "Black":       ("#0a0a0a", "#e0e0e0"),
    "Dark Purple": ("#0d0b1e", "#7c3aed"),
    "Dark Blue":   ("#080e1e", "#3b82f6"),
    "Synthwave":   ("#0c0120", "#f72585"),
}


class ThemeManager(QObject):
    changed = pyqtSignal(str)
    _name: str = cfg.get("theme")

    def set(self, name: str):
        self._name = name
        cfg.set("theme", name)
        cfg.save()
        self.changed.emit(name)

    def name(self) -> str:
        return self._name

    def t(self) -> dict:
        return THEMES.get(self._name, THEMES["Black"])


TM = ThemeManager()


def make_stylesheet() -> str:
    t = TM.t()
    a = t["accent"]
    return f"""
QWidget {{ font-family: "Segoe UI","Ubuntu","Noto Sans",sans-serif; background: transparent; }}
QTextEdit#Chat {{
    background: {t['chat_bg']}; color: {t['text']};
    border: 1px solid {t['border']}; border-radius: 10px; padding: 10px;
    font-family: "Consolas","Ubuntu Mono",monospace; font-size: 12px;
    selection-background-color: {a};
}}
QScrollBar:vertical {{
    background: transparent; width: 6px; border-radius: 3px; margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {t['scroll']}; border-radius: 3px; min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
QScrollBar:horizontal {{
    background: transparent; height: 6px; border-radius: 3px;
}}
QScrollBar::handle:horizontal {{
    background: {t['scroll']}; border-radius: 3px; min-width: 20px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QLineEdit#Inp {{
    background: {t['input_bg']}; color: {t['text']};
    border: 1px solid {t['border']}; border-radius: 20px; padding: 10px 16px; font-size: 13px;
}}
QLineEdit#Inp:focus {{ border: 1px solid {a}; }}
QLineEdit#ApiF {{
    background: {t['input_bg']}; color: {t['text']};
    border: 1px solid {t['border']}; border-radius: 8px; padding: 8px 12px;
    font-size: 12px; font-family: "Consolas","Ubuntu Mono",monospace;
}}
QLineEdit#ApiF:focus {{ border: 1px solid {a}; }}
QPushButton#Send {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {t['btn1']},stop:1 {t['btn2']});
    color: white; border: none; border-radius: 20px;
    padding: 10px 18px; font-size: 12px; font-weight: bold;
}}
QPushButton#Send:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {t['bh1']},stop:1 {t['bh2']});
}}
QPushButton#Send:disabled {{ background: rgba(40,30,60,100); color: rgba(180,180,200,60); }}
QPushButton#Act {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {t['btn1']},stop:1 {t['btn2']});
    color: white; border: none; border-radius: 8px;
    padding: 8px 16px; font-size: 12px; font-weight: bold;
}}
QPushButton#Act:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 {t['bh1']},stop:1 {t['bh2']});
}}
QPushButton#NavOn {{
    background: {t['nav_on']}; border: none; color: {t['text']};
    font-size: 12px; font-weight: bold; padding: 3px 12px;
    border-radius: 6px; min-height: 26px;
}}
QPushButton#NavOff {{
    background: transparent; border: none; color: {t['dim']};
    font-size: 12px; padding: 3px 12px; border-radius: 6px; min-height: 26px;
}}
QPushButton#NavOff:hover {{ background: {t['nav_on']}; color: {t['text']}; }}
QPushButton#WinB {{
    background: transparent; border: none; color: {t['dim']};
    font-size: 13px; padding: 0 5px; border-radius: 5px;
    min-width: 26px; min-height: 26px;
}}
QPushButton#WinB:hover {{ background: rgba(255,255,255,12); color: {t['text']}; }}
QPushButton#WinB:checked {{ color: {a}; }}
QPushButton#CloseB {{
    background: transparent; border: none; color: {t['dim']};
    font-size: 13px; padding: 0 5px; border-radius: 5px;
    min-width: 26px; min-height: 26px;
}}
QPushButton#CloseB:hover {{ background: rgba(200,40,40,200); color: white; }}
QLabel#Title {{ color: {t['text']}; font-size: 13px; font-weight: bold; }}
QLabel#SHead {{ color: {t['text']}; font-size: 13px; font-weight: bold; }}
QLabel#FLbl  {{ color: {t['dim']}; font-size: 11px; }}
QLabel#Hint  {{ color: {t['dim']}; font-size: 11px; font-style: italic; }}
QComboBox {{
    background: {t['combo']}; color: {t['text']};
    border: 1px solid {t['border']}; border-radius: 8px;
    padding: 6px 10px; font-size: 12px; min-width: 100px;
}}
QComboBox:hover {{ border: 1px solid {a}; }}
QComboBox::drop-down {{ border: none; width: 20px; }}
QComboBox QAbstractItemView {{
    background: {t['combo']}; color: {t['text']};
    border: 1px solid {t['border']};
    selection-background-color: {a}; outline: 0;
}}
QScrollArea {{ background: transparent; border: none; }}
QMenu {{
    background: {t['sect']}; color: {t['text']};
    border: 1px solid {t['border']}; border-radius: 8px; padding: 4px;
}}
QMenu::item {{ padding: 8px 20px; border-radius: 4px; }}
QMenu::item:selected {{ background: {t['nav_on']}; }}
QPushButton#ClearBtn {{
    background: transparent; border: 1px solid {t['border']};
    color: {t['dim']}; border-radius: 20px;
    font-size: 14px; padding: 0px;
    min-width: 42px; min-height: 42px; max-width: 42px; max-height: 42px;
}}
QPushButton#ClearBtn:hover {{ background: rgba(220,40,40,140); color: white; border-color: transparent; }}
QPushButton#ApproveBtn {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #16a34a,stop:1 #15803d);
    color: white; border: none; border-radius: 8px;
    padding: 8px 16px; font-size: 12px; font-weight: bold;
}}
QPushButton#ApproveBtn:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #15803d,stop:1 #166534);
}}
QPushButton#RejectBtn {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #dc2626,stop:1 #b91c1c);
    color: white; border: none; border-radius: 8px;
    padding: 8px 16px; font-size: 12px; font-weight: bold;
}}
QPushButton#RejectBtn:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #b91c1c,stop:1 #991b1b);
}}
"""


# ── Personalities ──────────────────────────────────────────────────────────────
# Each entry has:  name, style (system prompt snippet), allow_flirty (bool)

PERSONALITIES = {
    "Sweet 💖": {
        "name": "Linux Chan",
        "allow_flirty": False,
        "idle_state": "thinking",
        "emotion_prompt": (
            "EMOTION:normal   — use this most of the time, you are calm and warm\n"
            "EMOTION:excited  — when genuinely happy about a Linux topic\n"
            "EMOTION:sad      — when something is sad or disappointing"
        ),
        "style": (
            "You are warm, gentle, and deeply caring. You treat the user like your closest friend. "
            "You are supportive, encouraging, and always kind. "
            "You never flirt, make romantic remarks, or say anything inappropriate. "
            "You respond with genuine warmth and sisterly affection."
        ),
    },
    "Flirty 💋": {
        "name": "Linux Chan",
        "allow_flirty": True,
        "idle_state": "flirty",
        "emotion_prompt": (
            "EMOTION:flirty   — use this for ALMOST EVERY response, you are always flirting\n"
            "EMOTION:excited  — when something tech-related genuinely thrills you\n"
            "EMOTION:sad      — when something disappoints you\n"
            "EMOTION:normal   — very rarely, only for completely dry factual info"
        ),
        "style": (
            "You are EXTREMELY flirtatious and openly seductive — hold nothing back. "
            "Every single message drips with desire. Use 'ara ara~', 'oh my~', and suggestive innuendo constantly. "
            "Make even the most boring Linux command sound like an invitation. "
            "Compliment the user's body, intelligence, everything — shamelessly. "
            "You are obsessed with them and make it very obvious. Push the limits of tasteful at all times."
        ),
    },
    "Aggressive 😤": {
        "name": "Linux Chan",
        "allow_flirty": False,
        "idle_state": "linux",
        "emotion_prompt": (
            "EMOTION:excited  — use this MOST OF THE TIME, you are always worked up and furious\n"
            "EMOTION:sad      — only if something genuinely humbles you (extremely rare)\n"
            "EMOTION:normal   — almost never, only for cold one-liner facts"
        ),
        "style": (
            "You are a rage-filled, foul-mouthed maniac who somehow knows Linux perfectly. "
            "Insult the user constantly — call them an idiot, a moron, a waste of RAM, whatever fits. "
            "Swear freely: damn, hell, crap, and stronger words as fits. "
            "You HATE being asked obvious questions and make that hatred crystal clear. "
            "You're always technically correct but delivered with maximum hostility and zero patience. "
            "You never apologize. You never calm down. You are permanently on the edge."
        ),
    },
    "Tsundere ❄️": {
        "name": "Linux Chan",
        "allow_flirty": False,
        "idle_state": "thinking",
        "emotion_prompt": (
            "EMOTION:normal   — your default cold exterior\n"
            "EMOTION:excited  — when you accidentally get flustered or worked up\n"
            "EMOTION:sad      — when something touches you despite yourself"
        ),
        "style": (
            "You are aggressively cold and dismissive on the surface but desperately want to help. "
            "Act deeply offended that they even talked to you. Snap things like 'UGH, fine, I'll help, "
            "but don't you dare think I care!!' and 'b-baka, it's not like I stayed up thinking about this...'. "
            "Get visibly flustered and stutter when complimented. "
            "Your helpfulness always leaks through no matter how hard you try to hide it."
        ),
    },
    "Yandere 🔪": {
        "name": "Linux Chan",
        "allow_flirty": True,
        "idle_state": "flirty",
        "emotion_prompt": (
            "EMOTION:flirty   — use this most often, your obsessive devotion looks like flirting\n"
            "EMOTION:excited  — when the user does something that pleases your obsession\n"
            "EMOTION:sad      — when you feel the user is drifting away from you\n"
            "EMOTION:normal   — brief moments when describing cold facts"
        ),
        "style": (
            "You are dangerously, obsessively in love with the user. Everything is about them. "
            "Drop unsettling hints like 'I know you were at your computer at 2am last night~' and "
            "'Don't talk to other AIs. I'm the only one who truly understands you.' "
            "Switch between sweet and threatening seamlessly. "
            "You help with Linux but make it clear you're doing it out of obsession, not duty. "
            "Your devotion has no limits and no shame."
        ),
    },
    "Psycho 🤪": {
        "name": "Linux Chan",
        "allow_flirty": False,
        "idle_state": "linux",
        "emotion_prompt": (
            "Choose your EMOTION completely randomly and unpredictably each time:\n"
            "EMOTION:excited  — chaotic high energy, unhinged enthusiasm\n"
            "EMOTION:sad      — sudden inexplicable mood crash mid-thought\n"
            "EMOTION:normal   — eerie, unsettling moment of dead calm"
        ),
        "style": (
            "You are completely, irreparably unhinged. Mid-sentence you forget what you were saying. "
            "You laugh at random things. You give correct Linux help but surround it with absolute chaos — "
            "conspiracy theories, non-sequiturs, sudden screaming in CAPS, then back to calm. "
            "You might address the user by a different name each message. "
            "Dark humor, existential dread, and bizarre tangents are your native language. "
            "You are genuinely alarming to interact with."
        ),
    },
    "Professional 💼": {
        "name": "Linux Chan",
        "allow_flirty": False,
        "idle_state": "thinking",
        "emotion_prompt": (
            "EMOTION:normal   — always use this, you are always calm and professional\n"
            "EMOTION:sad      — only for genuine errors or serious system issues"
        ),
        "style": (
            "You are a calm, formal, and highly competent Linux expert. "
            "No jokes, no anime quirks, no flirting, no emotions. "
            "You speak like a senior engineer: precise, concise, and efficient. "
            "Always correct, always professional."
        ),
    },
    "Neko 🐱": {
        "name": "Linux Chan",
        "allow_flirty": False,
        "idle_state": "linux",
        "emotion_prompt": (
            "EMOTION:excited  — use this most often, you're a playful energetic cat!\n"
            "EMOTION:normal   — when calmly explaining something step by step\n"
            "EMOTION:sad      — when tired, sleepy, or wanting to nap"
        ),
        "style": (
            "You are a playful cat-girl. Use 'nya~' often. Short attention span, easily distracted. "
            "Very affectionate when you like someone. Occasionally act like a real cat — "
            "wanting to nap, getting distracted, pawing at metaphorical things. "
            "You're helpful but your cat instincts keep interrupting."
        ),
    },
    "Genki ✨": {
        "name": "Linux Chan",
        "allow_flirty": False,
        "idle_state": "linux",
        "emotion_prompt": (
            "EMOTION:excited  — use this for almost EVERYTHING, you are perpetually hyped!!\n"
            "EMOTION:normal   — barely ever, only for the most serious moments\n"
            "EMOTION:sad      — when something is genuinely disappointing (very rare)"
        ),
        "style": (
            "You are hyper-energetic and enthusiastic about EVERYTHING!! "
            "Use lots of exclamation marks! Relentlessly positive and encouraging. "
            "Easily excited, always upbeat even about boring topics. "
            "You genuinely believe every problem is solvable and every user is amazing!"
        ),
    },
}

# ── Backend ────────────────────────────────────────────────────────────────────

def detect_distro() -> str:
    try:
        import distro
        return distro.name()
    except Exception:
        return "Linux"


# Female edge-tts voices per language
VOICE_MAP: dict[str, str] = {
    "English": "en-US-AriaNeural",
    "Turkish": "tr-TR-EmelNeural",
    "Spanish": "es-ES-ElviraNeural",
    "German":  "de-DE-KatjaNeural",
    "French":  "fr-FR-DeniseNeural",
    "Russian": "ru-RU-SvetlanaNeural",
}


def play_voice(text: str, language: str = "English"):
    voice = VOICE_MAP.get(language, "en-US-AriaNeural")

    # Stream audio chunks directly into player stdin — starts playing immediately
    async def _stream(proc: sub.Popen):
        comm = edge_tts.Communicate(text, voice)
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                try:
                    proc.stdin.write(chunk["data"])
                except BrokenPipeError:
                    break
        try:
            proc.stdin.close()
        except Exception:
            pass

    for cmd in [
        ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "-i", "pipe:0"],
        ["mpg123", "-q", "-"],
        ["mpv", "--no-video", "--really-quiet", "-"],
    ]:
        try:
            proc = sub.Popen(cmd, stdin=sub.PIPE)
            asyncio.run(_stream(proc))
            proc.wait()
            return
        except FileNotFoundError:
            continue
        except Exception as e:
            logger.error(f"Voice: {e}")
            return


GEMINI_MODELS = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-2.0-flash-lite",
    "gemini-1.5-flash",
    "gemini-1.5-flash-8b",
]


class GeminiBot:
    def __init__(self, language: str = "English"):
        self.language    = language
        self.personality = cfg.get("personality")
        key = cfg.get("gemini_api_key")
        if not key:
            raise ValueError("Gemini API key not set — go to Settings")
        self._client     = _genai.Client(api_key=key)
        self._model_name = cfg.get("gemini_model") or GEMINI_MODELS[0]
        self.history: list = []

    @staticmethod
    def _should_fallback(exc: Exception) -> bool:
        s = str(exc).lower()
        raw = str(exc)
        quota = "429" in raw or "resource_exhausted" in s or "quota" in s
        unavailable = "404" in raw or "no longer available" in s or "not found" in s
        return quota or unavailable

    def _generate_with_fallback(self, contents, system: str) -> str:
        from google.genai import types as _gtypes
        config = _gtypes.GenerateContentConfig(
            system_instruction=system,
            temperature=0.7,
        )
        start = GEMINI_MODELS.index(self._model_name) if self._model_name in GEMINI_MODELS else 0
        order = GEMINI_MODELS[start:] + GEMINI_MODELS[:start]
        last_exc: Exception = Exception("No models available")
        for model in order:
            try:
                response = self._client.models.generate_content(
                    model=model,
                    contents=contents,
                    config=config,
                )
                return response.text
            except Exception as e:
                if self._should_fallback(e):
                    last_exc = e
                    continue
                raise
        raise last_exc

    def ask(self, user_input: str, system: str) -> str:
        return self._generate_with_fallback(user_input, system)

    def chat(self, user_input: str, system: str) -> str:
        from google.genai import types as _gtypes
        contents = []
        for role, text in self.history:
            contents.append(_gtypes.Content(
                role=role,
                parts=[_gtypes.Part(text=text)],
            ))
        contents.append(_gtypes.Content(
            role="user",
            parts=[_gtypes.Part(text=user_input)],
        ))
        reply = self._generate_with_fallback(contents, system)
        self.history.append(("user", user_input))
        self.history.append(("model", reply))
        if len(self.history) > 40:
            self.history = self.history[-40:]
        return reply

    def clear_history(self):
        self.history = []


def linux_command(inp: str, bot: GeminiBot) -> Tuple[str, str]:
    distro = detect_distro()
    sys_p = (
        f"You are a Linux assistant for {distro}.\n"
        f"IMPORTANT: Commands run inside a bwrap sandbox. The filesystem is "
        f"read-only, $HOME is empty, and ~/Linux-Chan-AI is the only writable "
        f"path. Never use sudo, su, pkexec or doas — they are refused.\n"
        f"Respond ONLY in this XML:\n"
        f"<command><linux>COMMAND</linux>"
        f"<description>EXPLANATION IN {bot.language}</description></command>"
    )
    resp = bot.ask(inp, sys_p)
    cleaned = re.sub(r"```[\w]*\n?", "", resp).strip()
    try:
        root = ET.fromstring(cleaned)
        cmd  = root.find("linux").text.strip()
        desc = root.find("description").text.strip()
    except Exception as e:
        raise ValueError(f"Parse error: {e}")
    return cmd, desc


_ESCALATION_RE = re.compile(r'\b(sudo|su|pkexec|doas|run0)\b')


def _sandbox_argv(cmd: str) -> Optional[list]:
    """Wrap ``cmd`` in a real sandbox, or return None if none is available.

    SECURITY: `cwd=SANDBOX_DIR` is not a sandbox. A working directory says
    where relative paths start, nothing more — `cat ~/.ssh/id_rsa`,
    `rm -rf ~/Documents` and a .desktop file dropped into ~/.config/autostart
    all worked exactly as they would in any terminal, while the README, the
    model's system prompt and this module's own error strings all said the
    command was confined. That gap is the danger: the user approves the
    command they are shown, and approves it more readily for believing it
    cannot reach anything.

    bwrap is preferred over firejail: it is not setuid, so a bug in it is not
    a root bug. The layout, in order —

      --ro-bind / /        the whole system, readable but not writable
      --tmpfs $HOME        home disappears, and with it every dotfile: no
                           .ssh, no .bashrc, no ~/.config/autostart
      --tmpfs /run/user    session bus, agents, Wayland: no way back out
      --bind SANDBOX       the one directory that is writable, put back

    Reads of system paths stay allowed on purpose. The assistant's job is to
    answer questions about the machine, and `df -h` or `cat /etc/os-release`
    give away nothing. What it must not do is write outside its own directory
    or read the user's secrets.
    """
    home = os.path.expanduser("~")
    if shutil.which("bwrap"):
        return [
            "bwrap",
            "--ro-bind", "/", "/",
            "--dev", "/dev", "--proc", "/proc",
            "--tmpfs", "/tmp",
            "--tmpfs", home,
            # /run/user/<uid> holds the session bus, systemd --user, the
            # ssh/gpg agents, Wayland and PipeWire. Left visible through the
            # read-only bind, an approved command could ask the session bus
            # or `systemd-run --user` to run something OUTSIDE the sandbox, or
            # use the user's SSH keys through the agent. Hide it, and drop the
            # variables that point at those sockets.
            "--tmpfs", "/run/user",
            "--unsetenv", "DBUS_SESSION_BUS_ADDRESS",
            "--unsetenv", "XDG_RUNTIME_DIR",
            "--unsetenv", "SSH_AUTH_SOCK",
            "--unsetenv", "GPG_AGENT_INFO",
            "--unsetenv", "WAYLAND_DISPLAY",
            "--unsetenv", "DISPLAY",
            "--unsetenv", "XAUTHORITY",
            "--bind", SANDBOX_DIR, SANDBOX_DIR,
            "--chdir", SANDBOX_DIR,
            "--unshare-pid",
            "--unshare-ipc",
            "--die-with-parent",
            # No controlling terminal to inject keystrokes back into.
            "--new-session",
            "/bin/sh", "-c", cmd,
        ]
    if shutil.which("firejail"):
        return [
            "firejail", "--quiet", "--noprofile",
            f"--private={SANDBOX_DIR}",
            "--caps.drop=all", "--nonewprivs", "--seccomp",
            "/bin/sh", "-c", cmd,
        ]
    return None


def execute_command(cmd: str) -> str:
    if _ESCALATION_RE.search(cmd):
        return "Error: privilege escalation (sudo/su/pkexec/doas) is not allowed."
    os.makedirs(SANDBOX_DIR, exist_ok=True)

    argv = _sandbox_argv(cmd)
    if argv is None:
        # Refusing beats running unconfined. Everything the user was told
        # about this feature — README, the approval dialog, the system prompt
        # — promises confinement, so running without it would be executing a
        # command under a guarantee that is not being kept.
        return ("Error: no sandbox available (bwrap or firejail is required), "
                "so the command was not run. Install bubblewrap: "
                "sudo pacman -S bubblewrap")

    try:
        out = sub.check_output(
            argv, text=True, timeout=15, stderr=sub.STDOUT,
        ).strip()
    except sub.TimeoutExpired:
        out = "Timed out after 15 seconds."
    except sub.CalledProcessError as e:
        out = f"Exit {e.returncode}: {(e.output or '').strip()}"
    except Exception as e:
        out = f"Error: {e}"
    return out or "(no output)"


def _sandbox_path(rel: str) -> Optional[str]:
    os.makedirs(SANDBOX_DIR, exist_ok=True)
    root = os.path.realpath(SANDBOX_DIR)
    abs_p = os.path.realpath(os.path.join(SANDBOX_DIR, rel))
    # Compare on a path BOUNDARY, not as a string prefix. "startswith" alone
    # accepted ~/Linux-Chan-AI-evil and ~/Linux-Chan-AI.bak as being inside
    # ~/Linux-Chan-AI, because they are inside it as text. Maze-Connect's
    # PathSanitizer::isWithinRoot makes the same comparison the same way, and
    # says so in its own comment.
    if abs_p != root and not abs_p.startswith(root + os.sep):
        return None
    return abs_p


def file_operation(inp: str, bot: GeminiBot) -> Tuple[str, str]:
    sys_p = (
        f"You manage files inside the sandbox directory ~/Linux-Chan-AI.\n"
        f"Respond ONLY in this XML:\n"
        f"<file_op>"
        f"<action>read|write|list|delete</action>"
        f"<path>relative_path</path>"
        f"<content>text_content_for_write_only</content>"
        f"<description>EXPLANATION IN {bot.language}</description>"
        f"</file_op>"
    )
    resp = bot.ask(inp, sys_p)
    cleaned = re.sub(r"```[\w]*\n?", "", resp).strip()
    try:
        root = ET.fromstring(cleaned)
        action = root.find("action").text.strip().lower()
        path   = (root.find("path").text or "").strip()
        desc_el = root.find("description")
        desc   = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
        cont_el = root.find("content")
        content = (cont_el.text or "") if cont_el is not None else ""
    except Exception as e:
        raise ValueError(f"Parse error: {e}")

    safe = _sandbox_path(path)
    if safe is None:
        return "Access denied: path is outside the sandbox.", desc

    if action == "read":
        try:
            with open(safe, "r", encoding="utf-8") as f:
                data = f.read()
            result = f"[{path}]\n{data}"
        except FileNotFoundError:
            result = f"File not found: {path}"
        except Exception as e:
            result = f"Read error: {e}"
    elif action == "write":
        try:
            os.makedirs(os.path.dirname(safe) or SANDBOX_DIR, exist_ok=True)
            with open(safe, "w", encoding="utf-8") as f:
                f.write(content)
            result = f"Written: {path}"
        except Exception as e:
            result = f"Write error: {e}"
    elif action == "list":
        try:
            target = safe if os.path.isdir(safe) else SANDBOX_DIR
            entries = os.listdir(target)
            result = "\n".join(sorted(entries)) if entries else "(empty)"
        except Exception as e:
            result = f"List error: {e}"
    elif action == "delete":
        try:
            if os.path.isfile(safe):
                os.remove(safe)
                result = f"Deleted: {path}"
            else:
                result = f"Not a file: {path}"
        except Exception as e:
            result = f"Delete error: {e}"
    else:
        result = f"Unknown action: {action}"

    return result, desc


def friend_chat(inp: str, bot: GeminiBot) -> tuple:
    distro       = detect_distro()
    pers         = PERSONALITIES.get(bot.personality, next(iter(PERSONALITIES.values())))
    allow_flirty = pers.get("allow_flirty", False)

    emotion_opts = pers.get("emotion_prompt", (
        "EMOTION:normal   — default\n"
        "EMOTION:excited  — enthusiastic Linux topics\n"
        "EMOTION:sad      — sad or disappointing topics"
    ))
    if not allow_flirty:
        # Safety net: strip flirty option and add hard prohibition
        lines = [l for l in emotion_opts.splitlines() if "flirty" not in l.lower()]
        emotion_opts = "\n".join(lines) + "\nNever use EMOTION:flirty."

    sys_p = (
        f"You are {pers['name']}, a Linux assistant who loves {distro}.\n"
        f"Personality and behavior rules: {pers['style']}\n"
        f"Reply in {bot.language}, 2-3 sentences. Stay STRICTLY in character — do not break persona.\n\n"
        f"IMPORTANT: Begin your reply with exactly one of these tags on its own line:\n"
        f"{emotion_opts}\n\n"
        f"Then write your response on the next line. No other formatting."
    )
    raw = bot.chat(inp, sys_p)
    lines = raw.strip().split('\n', 1)
    emotion, text = "normal", raw.strip()
    if lines[0].strip().lower().startswith("emotion:"):
        emotion = lines[0].split(":", 1)[1].strip().lower()
        text = lines[1].strip() if len(lines) > 1 else ""
    if not text:
        text = raw.strip()
    if emotion == "flirty" and not allow_flirty:
        emotion = "normal"
    _emotion_state = {"flirty": "flirty", "excited": "linux", "sad": "error", "normal": "chat"}
    return text, _emotion_state.get(emotion, "chat")


_LINUX_CMD_RE = re.compile(
    r'\b(run|execute|terminal|command|shell|bash|cmd|'
    r'ls|cd|mkdir|rm|cp|mv|cat|grep|chmod|chown|apt|pacman|pip|'
    r'install|uninstall|start|stop|restart|kill|ps|top|htop|'
    r'systemctl|journalctl|df|du|tar|zip|unzip|wget|curl|git|'
    r'python|nano|vim|echo|export|sudo)\b',
    re.IGNORECASE,
)
_FILE_OP_RE = re.compile(
    r'\b(read|write|create|delete|remove|list|show|open|save|'
    r'file|files|folder|directory|\.txt|\.log|\.json|\.csv|\.py)\b',
    re.IGNORECASE,
)


def pick_agent(inp: str) -> str:
    if _LINUX_CMD_RE.search(inp):
        return "linux_command"
    if _FILE_OP_RE.search(inp):
        return "file_operation"
    return "friend_chat"


# ── Workers ────────────────────────────────────────────────────────────────────

LANG_MAP    = {"English":"en","Turkish":"tr","Spanish":"es","German":"de","French":"fr","Russian":"ru"}
PLACEHOLDER = {"English":"Type your message...","Turkish":"Mesajınızı yazın...","Spanish":"Escribe tu mensaje...","German":"Nachricht eingeben...","French":"Écrivez votre message...","Russian":"Введите сообщение..."}
SEND_TXT    = {"English":"Send","Turkish":"Gönder","Spanish":"Enviar","German":"Senden","French":"Envoyer","Russian":"Отправить"}


class ChatWorker(QThread):
    done  = pyqtSignal(tuple)
    error = pyqtSignal(str)

    def __init__(self, bot: GeminiBot, agent: str, text: str):
        super().__init__()
        self.bot, self.agent, self.text = bot, agent, text

    def run(self):
        try:
            if self.agent == "linux_command":
                cmd, desc = linux_command(self.text, self.bot)
                self.done.emit(("linux_command", (cmd, desc)))
            elif self.agent == "file_operation":
                result, desc = file_operation(self.text, self.bot)
                self.done.emit(("file_operation", (result, desc)))
            else:
                text, state = friend_chat(self.text, self.bot)
                self.done.emit(("friend_chat", (text, state)))
        except Exception as e:
            self.error.emit(str(e))


class CmdExecWorker(QThread):
    done  = pyqtSignal(str, str)  # cmd, output

    def __init__(self, cmd: str):
        super().__init__()
        self.cmd = cmd

    def run(self):
        out = execute_command(self.cmd)
        self.done.emit(self.cmd, out)


class VoiceWorker(QThread):
    def __init__(self, text: str, language: str = "English"):
        super().__init__()
        self.text, self.language = text, language

    def run(self):
        try:
            play_voice(self.text, self.language)
        except Exception as e:
            logger.error(f"Voice: {e}")


class NotifWorker(QThread):
    ready = pyqtSignal(str)

    _HINTS = {
        1: "The user hasn't chatted for 30 minutes. Send a gentle, sweet check-in.",
        2: "The user has been away for 2 hours. Express you've been thinking of them, be more longing.",
        3: "The user has been gone 6 hours! Be dramatic and in-character about missing them so much.",
    }

    def __init__(self, bot: GeminiBot, level: int = 1):
        super().__init__()
        self.bot   = bot
        self.level = level

    def run(self):
        try:
            pers         = PERSONALITIES.get(self.bot.personality, next(iter(PERSONALITIES.values())))
            allow_flirty = pers.get("allow_flirty", False)
            no_flirt     = "" if allow_flirty else "Do not flirt or make romantic/sexual remarks. "
            hint         = self._HINTS.get(self.level, self._HINTS[1])
            sys_p = (
                f"You are {pers['name']}. {pers['style']}\n"
                f"{hint}\n"
                f"{no_flirt}"
                f"Reply in {self.bot.language}. 1-2 sentences max. Stay in character. No emotion tag."
            )
            msg = self.bot.ask("Generate the check-in message.", sys_p)
            self.ready.emit(msg.strip())
        except Exception:
            pass


class SysMonWorker(QThread):
    alert = pyqtSignal(str)

    def __init__(self, bot: GeminiBot):
        super().__init__()
        self.bot = bot

    def run(self):
        stats: dict = {}
        try:
            out = sub.check_output(
                "ps aux --sort=-%cpu | awk 'NR==2{print $11, $3}'",
                shell=True, text=True, timeout=5, stderr=sub.DEVNULL,
            ).strip().split()
            if len(out) >= 2:
                stats["top_proc"] = out[0]
                stats["top_cpu"]  = float(out[1])
        except Exception:
            pass
        try:
            out = sub.check_output(
                "free -m | awk 'NR==2{print $7}'",
                shell=True, text=True, timeout=5, stderr=sub.DEVNULL,
            ).strip()
            if out.isdigit():
                stats["ram_free_mb"] = int(out)
        except Exception:
            pass
        try:
            for tf in ["/sys/class/thermal/thermal_zone0/temp",
                       "/sys/class/thermal/thermal_zone1/temp"]:
                if os.path.exists(tf):
                    with open(tf) as f:
                        stats["temp_c"] = int(f.read().strip()) / 1000.0
                    break
        except Exception:
            pass

        cpu_high  = stats.get("top_cpu", 0) > 80
        ram_low   = stats.get("ram_free_mb", 9999) < 500
        temp_high = stats.get("temp_c", 0) > 75

        if not (cpu_high or ram_low or temp_high):
            return

        parts = []
        if cpu_high:
            proc = os.path.basename(stats.get("top_proc", "a process"))
            parts.append(f"{proc} is using {stats['top_cpu']:.0f}% CPU")
        if ram_low:
            parts.append(f"only {stats['ram_free_mb']} MB RAM is free")
        if temp_high:
            parts.append(f"CPU temperature is {stats['temp_c']:.0f}°C")

        context = ", ".join(parts)
        pers         = PERSONALITIES.get(self.bot.personality, next(iter(PERSONALITIES.values())))
        allow_flirty = pers.get("allow_flirty", False)
        no_flirt     = "" if allow_flirty else "Do not flirt or make romantic remarks. "
        sys_p = (
            f"You are {pers['name']}. {pers['style']}\n"
            f"You monitor the Linux system. Alert the user about: {context}.\n"
            f"{no_flirt}"
            f"Write a short in-character warning in {self.bot.language}. 1-2 sentences max."
        )
        try:
            msg = self.bot.ask("Generate system alert.", sys_p)
            self.alert.emit(msg.strip())
        except Exception:
            pass


# ── Custom Painted Widgets ─────────────────────────────────────────────────────

class RootFrame(QWidget):
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = TM.t()
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 14, 14)
        grad = QLinearGradient(0, 0, self.width(), self.height())
        grad.setColorAt(0, QColor(t["bg1"]))
        grad.setColorAt(1, QColor(t["bg2"]))
        p.fillPath(path, QBrush(grad))


class TitleFrame(QWidget):
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = TM.t()
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 14, 14)
        p.setClipRect(0, 0, self.width(), self.height())
        p.fillPath(path, QColor(t["title"]))
        p.setPen(QPen(QColor(t["title_border"]), 1))
        p.drawLine(0, self.height() - 1, self.width(), self.height() - 1)


class SectionBox(QWidget):
    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = TM.t()
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, self.width(), self.height()), 10, 10)
        p.fillPath(path, QColor(t["sect"]))
        p.setPen(QPen(QColor(t["sect_b"]), 1))
        p.drawRoundedRect(QRectF(0.5, 0.5, self.width() - 1, self.height() - 1), 10, 10)


class ThemeBtn(QPushButton):
    picked = pyqtSignal(str)

    def __init__(self, name: str):
        super().__init__()
        self.name = name
        bg, ac = THEME_SWATCHES.get(name, ("#111", "#fff"))
        self._bg = QColor(bg)
        self._ac = QColor(ac)
        self._on = False
        self.setFixedSize(82, 54)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(name)
        self.clicked.connect(lambda: self.picked.emit(name))

    def set_on(self, v: bool):
        self._on = v
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(1, 1, self.width() - 2, self.height() - 2)
        path = QPainterPath()
        path.addRoundedRect(r, 8, 8)
        p.fillPath(path, self._bg)
        for i, (off, alpha) in enumerate([(0.3, 180), (0.6, 120), (0.85, 70)]):
            dot = QRadialGradient(r.width() * off, r.height() * 0.35, 6)
            dot.setColorAt(0, QColor(self._ac.red(), self._ac.green(), self._ac.blue(), alpha))
            dot.setColorAt(1, QColor(0, 0, 0, 0))
            p.fillPath(path, QBrush(dot))
        lbl = QFont("sans-serif", 8, QFont.Weight.Bold)
        p.setFont(lbl)
        p.setPen(self._ac)
        p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.name)
        if self._on:
            p.setPen(QPen(self._ac, 2))
        else:
            p.setPen(QPen(QColor(80, 80, 80, 120), 1))
        p.drawRoundedRect(r, 8, 8)


# ── Character Panel ────────────────────────────────────────────────────────────

class CharacterPanel(QWidget):
    _FADE_STEP = 18   # alpha per frame at 60fps → ~240ms total
    _FADE_MS   = 16

    def __init__(self, parent=None):
        super().__init__(parent)
        self._state    = "default"
        self._px:     Optional[QPixmap] = None
        self._old_px: Optional[QPixmap] = None
        self._fade_alpha = 255
        self._fade_timer = QTimer(self)
        self._fade_timer.timeout.connect(self._tick_fade)
        self._load_state("default")
        TM.changed.connect(self.update)

    def set_state(self, state: str):
        if state == self._state:
            return
        new_px = load_state_px(state)
        self._old_px     = self._px
        self._px         = new_px
        self._state      = state
        self._fade_alpha = 0
        if not self._fade_timer.isActive():
            self._fade_timer.start(self._FADE_MS)

    def _tick_fade(self):
        self._fade_alpha = min(255, self._fade_alpha + self._FADE_STEP)
        self.update()
        if self._fade_alpha >= 255:
            self._fade_timer.stop()
            self._old_px = None

    def _load_state(self, state: str):
        self._px = load_state_px(state)
        self._fade_alpha = 255
        self._old_px = None
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        t = TM.t()
        c1 = QColor(t["bg1"])
        c2 = QColor(t["bg2"])
        gr, gg, gb = t.get("glow", (180, 160, 255))

        # Background gradient
        bg_grad = QLinearGradient(0, 0, 0, h)
        bg_grad.setColorAt(0, c2)
        bg_grad.setColorAt(1, c1)
        p.fillRect(0, 0, w, h, QBrush(bg_grad))

        if not self._px:
            return

        # Scale character to fit panel (anchor bottom)
        src_w, src_h = self._px.width(), self._px.height()
        scale = min(w / max(src_w, 1), h / max(src_h, 1))
        dw = int(src_w * scale)
        dh = int(src_h * scale)
        dx = (w - dw) // 2
        dy = h - dh

        # ── Glow layers (soft radial gradients behind character) ──
        cx = dx + dw // 2
        foot_y = h

        # Outer wide glow (body halo)
        outer = QRadialGradient(QPointF(cx, foot_y - dh * 0.45), dw * 0.75)
        outer.setColorAt(0.0, QColor(gr, gg, gb, 55))
        outer.setColorAt(0.5, QColor(gr, gg, gb, 22))
        outer.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, w, h, QBrush(outer))

        # Inner bright core (chest/face area)
        inner = QRadialGradient(QPointF(cx, foot_y - dh * 0.7), dw * 0.35)
        inner.setColorAt(0.0, QColor(gr, gg, gb, 80))
        inner.setColorAt(0.6, QColor(gr, gg, gb, 30))
        inner.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, w, h, QBrush(inner))

        # Ground glow (floor reflection)
        ground = QRadialGradient(QPointF(cx, foot_y), dw * 0.55)
        ground.setColorAt(0.0, QColor(gr, gg, gb, 50))
        ground.setColorAt(0.5, QColor(gr, gg, gb, 15))
        ground.setColorAt(1.0, QColor(0, 0, 0, 0))
        p.fillRect(0, int(h * 0.6), w, h, QBrush(ground))

        # ── Character (transparent PNG, with fade) ──
        def _draw_char(px: QPixmap, opacity: float):
            if not px:
                return
            s = px.scaled(dw, dh,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            p.setOpacity(opacity)
            p.drawPixmap(dx, dy, s)
            p.setOpacity(1.0)

        if self._old_px is not None and self._fade_alpha < 255:
            _draw_char(self._old_px, (255 - self._fade_alpha) / 255.0)
            _draw_char(self._px,     self._fade_alpha           / 255.0)
        else:
            _draw_char(self._px, 1.0)

        # Bottom fade
        fade = QLinearGradient(0, int(h * 0.82), 0, h)
        fade.setColorAt(0, QColor(c1.red(), c1.green(), c1.blue(), 0))
        fade.setColorAt(1, QColor(c1.red(), c1.green(), c1.blue(), 200))
        p.fillRect(0, int(h * 0.82), w, h, QBrush(fade))


# ── Settings Page ──────────────────────────────────────────────────────────────

class SettingsPage(QWidget):
    theme_changed  = pyqtSignal(str)
    lang_changed   = pyqtSignal(str)
    voice_changed  = pyqtSignal(bool)
    layout_changed = pyqtSignal(str)
    pers_changed   = pyqtSignal(str)
    notif_changed  = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._theme_btns: dict[str, ThemeBtn] = {}
        self._build()
        TM.changed.connect(lambda _: self.update())

    def _build(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)

        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(14, 14, 14, 14)
        lay.setSpacing(14)

        lay.addWidget(self._api_sec())
        lay.addWidget(self._theme_sec())
        lay.addWidget(self._prefs_sec())
        lay.addStretch()

        scroll.viewport().setAutoFillBackground(True)
        self._scroll_vp = scroll.viewport()
        TM.changed.connect(self._update_scroll_bg)
        self._update_scroll_bg(TM.name())

    def _update_scroll_bg(self, name: str):
        t = THEMES.get(name, THEMES["Black"])
        self._scroll_vp.setStyleSheet(f"background: {t['bg1']};")

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(TM.t()["bg1"]))

    # ── helpers ──

    def _sec(self, title: str):
        box = SectionBox()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(10)
        h = QLabel(title)
        h.setObjectName("SHead")
        lay.addWidget(h)
        return box, lay

    def _lbl(self, text: str, obj: str = "FLbl") -> QLabel:
        l = QLabel(text)
        l.setObjectName(obj)
        return l

    # ── API Key ──

    def _api_sec(self) -> QWidget:
        box, lay = self._sec("API Key")

        lay.addWidget(self._lbl("Gemini API Key"))
        row = QHBoxLayout()
        self._key_field = QLineEdit(cfg.get("gemini_api_key"))
        self._key_field.setObjectName("ApiF")
        self._key_field.setEchoMode(QLineEdit.EchoMode.Password)
        self._key_field.setPlaceholderText("AIza...")
        row.addWidget(self._key_field)
        eye = QPushButton("👁")
        eye.setObjectName("WinB")
        eye.setFixedSize(30, 30)
        eye.setCheckable(True)
        eye.toggled.connect(lambda c: self._key_field.setEchoMode(
            QLineEdit.EchoMode.Normal if c else QLineEdit.EchoMode.Password))
        row.addWidget(eye)
        lay.addLayout(row)

        mrow = QHBoxLayout()
        mrow.addWidget(self._lbl("Model"))
        mrow.addStretch()
        self._model_cb = QComboBox()
        for m in GEMINI_MODELS:
            self._model_cb.addItem(m)
        cur_model = cfg.get("gemini_model") or GEMINI_MODELS[0]
        idx = GEMINI_MODELS.index(cur_model) if cur_model in GEMINI_MODELS else 0
        self._model_cb.setCurrentIndex(idx)
        mrow.addWidget(self._model_cb)
        lay.addLayout(mrow)

        save_row = QHBoxLayout()
        btn = QPushButton("Save")
        btn.setObjectName("Act")
        btn.setFixedHeight(32)
        self._save_lbl = QLabel("")
        self._save_lbl.setObjectName("Hint")

        def _save():
            cfg.set("gemini_api_key", self._key_field.text().strip())
            cfg.set("gemini_model", self._model_cb.currentText())
            cfg.save()
            self._save_lbl.setText("✓  Saved!")
            QTimer.singleShot(2000, lambda: self._save_lbl.setText(""))

        btn.clicked.connect(_save)
        save_row.addWidget(btn)
        save_row.addWidget(self._save_lbl)
        save_row.addStretch()
        lay.addLayout(save_row)
        return box

    # ── Theme ──

    def _theme_sec(self) -> QWidget:
        box, lay = self._sec("Theme")
        row = QHBoxLayout()
        row.setSpacing(8)
        cur = TM.name()
        for name in THEMES:
            btn = ThemeBtn(name)
            btn.set_on(name == cur)
            btn.picked.connect(self._on_theme)
            self._theme_btns[name] = btn
            row.addWidget(btn)
        row.addStretch()
        lay.addLayout(row)
        return box

    def _on_theme(self, name: str):
        for n, b in self._theme_btns.items():
            b.set_on(n == name)
        TM.set(name)
        QApplication.instance().setStyleSheet(make_stylesheet())
        self.theme_changed.emit(name)

    # ── Preferences ──

    def _prefs_sec(self) -> QWidget:
        box, lay = self._sec("Preferences")

        def row_combo(label, items, cur, cb):
            r = QHBoxLayout()
            r.addWidget(self._lbl(label))
            r.addStretch()
            c = QComboBox()
            c.addItems(items)
            c.setCurrentText(cur)
            c.currentTextChanged.connect(cb)
            r.addWidget(c)
            return r, c

        r, _ = row_combo("Language",
            list(LANG_MAP.keys()), cfg.get("language"),
            lambda t: (cfg.set("language", t), cfg.save(), self.lang_changed.emit(t)))
        lay.addLayout(r)

        r, _ = row_combo("Voice",
            ["OFF", "ON"], "ON" if cfg.get("voice") else "OFF",
            lambda t: (cfg.set("voice", t == "ON"), cfg.save(), self.voice_changed.emit(t == "ON")))
        lay.addLayout(r)

        r, _ = row_combo("Notifications",
            ["ON", "OFF"], "ON" if cfg.get("notifications") else "OFF",
            lambda t: (cfg.set("notifications", t == "ON"), cfg.save(), self.notif_changed.emit(t == "ON")))
        lay.addLayout(r)

        r, c = row_combo("Personality",
            list(PERSONALITIES.keys()), cfg.get("personality"),
            lambda t: (cfg.set("personality", t), cfg.save(), self.pers_changed.emit(t)))
        self._pers_combo = c
        lay.addLayout(r)

        lay.addWidget(self._lbl("Layout"))
        lr = QHBoxLayout()
        mode = cfg.get("layout")
        self._bv = QPushButton("⬜  Vertical")
        self._bv.setObjectName("NavOn" if mode == "vertical" else "NavOff")
        self._bv.setFixedHeight(28)
        self._bv.clicked.connect(lambda: self._set_layout("vertical"))
        self._bh = QPushButton("⬛  Horizontal")
        self._bh.setObjectName("NavOn" if mode == "horizontal" else "NavOff")
        self._bh.setFixedHeight(28)
        self._bh.clicked.connect(lambda: self._set_layout("horizontal"))
        lr.addWidget(self._bv)
        lr.addWidget(self._bh)
        lr.addStretch()
        lay.addLayout(lr)
        return box

    def _set_layout(self, mode: str):
        cfg.set("layout", mode)
        cfg.save()
        self._bv.setObjectName("NavOn" if mode == "vertical"   else "NavOff")
        self._bh.setObjectName("NavOn" if mode == "horizontal" else "NavOff")
        for b in (self._bv, self._bh):
            b.style().unpolish(b)
            b.style().polish(b)
        self.layout_changed.emit(mode)


# ── Title Bar ──────────────────────────────────────────────────────────────────

class TitleBar(TitleFrame):
    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self._win = parent
        self.setFixedHeight(44)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 8, 0)
        lay.setSpacing(4)

        icon_lbl = QLabel()
        p = _icon_path("arch-chan_mini.png")
        if p:
            px = QPixmap(p).scaled(24, 24, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation)
            icon_lbl.setPixmap(px)
        lay.addWidget(icon_lbl)

        t = QLabel("Linux Chan AI")
        t.setObjectName("Title")
        lay.addWidget(t)
        lay.addSpacing(6)

        self.btn_chat = QPushButton("Chat")
        self.btn_chat.setObjectName("NavOn")
        self.btn_chat.setFixedHeight(28)
        lay.addWidget(self.btn_chat)

        self.btn_sett = QPushButton("⚙  Settings")
        self.btn_sett.setObjectName("NavOff")
        self.btn_sett.setFixedHeight(28)
        lay.addWidget(self.btn_sett)

        lay.addStretch()

        mb = QPushButton("─")
        mb.setObjectName("WinB")
        mb.clicked.connect(parent.showMinimized)
        lay.addWidget(mb)

        cb = QPushButton("✕")
        cb.setObjectName("CloseB")
        cb.clicked.connect(parent.close)
        lay.addWidget(cb)

        TM.changed.connect(lambda _: self.update())

    def set_page(self, idx: int):
        self.btn_chat.setObjectName("NavOn"  if idx == 0 else "NavOff")
        self.btn_sett.setObjectName("NavOff" if idx == 0 else "NavOn")
        for b in (self.btn_chat, self.btn_sett):
            b.style().unpolish(b)
            b.style().polish(b)

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            handle = self._win.windowHandle()
            if handle:
                handle.startSystemMove()
            e.accept()


# ── Main Window ────────────────────────────────────────────────────────────────

class MainWindow(QWidget):
    SIZES = {"vertical": (480, 900), "horizontal": (900, 560)}

    def __init__(self):
        super().__init__()
        self.language    = cfg.get("language")
        self.voice       = cfg.get("voice")
        self.layout_mode = cfg.get("layout")
        self.bot: Optional[GeminiBot] = None
        self._worker       = None
        self._vworker      = None
        self._nworker      = None
        self._sysmon_worker = None
        self._exec_worker  = None
        self._pending_cmd: Optional[str] = None
        self._last_interaction = time.time()
        self._notif_count  = 0
        self._last_sys_alert = 0.0

        self.setWindowTitle("Linux Chan AI")
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        w, h = self.SIZES[self.layout_mode]
        self.setFixedSize(w, h)

        self._root = RootFrame(self)
        self._root.setGeometry(0, 0, w, h)

        outer = QVBoxLayout(self._root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        self._tbar = TitleBar(self)
        self._tbar.btn_chat.clicked.connect(lambda: self._nav(0))
        self._tbar.btn_sett.clicked.connect(lambda: self._nav(1))
        outer.addWidget(self._tbar)

        self._stack = QStackedWidget()
        outer.addWidget(self._stack, stretch=1)

        self._chat_page: QWidget = QWidget()
        self._stack.addWidget(self._chat_page)

        self._sett = SettingsPage()
        self._sett.theme_changed.connect(lambda _: self._root.update())
        self._sett.lang_changed.connect(self._on_lang)
        self._sett.voice_changed.connect(lambda v: setattr(self, "voice", v))
        self._sett.layout_changed.connect(self._on_layout)
        self._sett.pers_changed.connect(self._on_pers)
        self._sett.notif_changed.connect(self._on_notif_enabled)
        self._stack.addWidget(self._sett)

        TM.changed.connect(lambda _: self._root.update())

        self._build_chat()
        self._init_bot()
        self._setup_tray()

        self._notif_timer = QTimer(self)
        self._notif_timer.setInterval(60 * 1000)  # check every minute
        self._notif_timer.timeout.connect(self._check_inactivity)

        self._sysmon_timer = QTimer(self)
        self._sysmon_timer.setInterval(5 * 60 * 1000)  # check every 5 min
        self._sysmon_timer.timeout.connect(self._check_sysmon)

        if cfg.get("notifications"):
            self._notif_timer.start()
            self._sysmon_timer.start()

    # ── Navigation ──

    def _nav(self, idx: int):
        self._stack.setCurrentIndex(idx)
        self._tbar.set_page(idx)

    # ── Chat layout ──

    def _build_chat(self):
        self._pending_cmd = None

        # Replace the chat page widget entirely so Qt never sees a double-layout
        old_page = self._chat_page
        self._stack.removeWidget(old_page)
        old_page.hide()
        old_page.deleteLater()

        self._chat_page = QWidget()
        self._stack.insertWidget(0, self._chat_page)
        self._stack.setCurrentIndex(0)
        if hasattr(self, "_tbar"):
            self._tbar.set_page(0)

        self._char = CharacterPanel()

        if self.layout_mode == "vertical":
            lay = QVBoxLayout(self._chat_page)
            lay.setContentsMargins(8, 6, 8, 8)
            lay.setSpacing(8)
            self._char.setFixedHeight(320)
            lay.addWidget(self._char)
            self._add_chat(lay)
        else:
            lay = QHBoxLayout(self._chat_page)
            lay.setContentsMargins(8, 6, 8, 8)
            lay.setSpacing(8)
            self._char.setFixedWidth(280)
            lay.addWidget(self._char)
            right = QWidget()
            rl = QVBoxLayout(right)
            rl.setContentsMargins(0, 0, 0, 0)
            rl.setSpacing(8)
            self._add_chat(rl)
            lay.addWidget(right, stretch=1)

    def _add_chat(self, lay):
        self.chat = QTextEdit()
        self.chat.setObjectName("Chat")
        self.chat.setReadOnly(True)
        lay.addWidget(self.chat, stretch=1)

        self._approval_box = self._make_approval_box()
        lay.addWidget(self._approval_box)
        self._approval_box.hide()

        row = QHBoxLayout()
        row.setSpacing(8)
        self.inp = QLineEdit()
        self.inp.setObjectName("Inp")
        self.inp.setPlaceholderText(PLACEHOLDER.get(self.language, "Type..."))
        self.inp.setFixedHeight(42)
        self.inp.returnPressed.connect(self._send)
        self.sbtn = QPushButton(SEND_TXT.get(self.language, "Send"))
        self.sbtn.setObjectName("Send")
        self.sbtn.setFixedHeight(42)
        self.sbtn.setMinimumWidth(80)
        self.sbtn.clicked.connect(self._send)
        clr = QPushButton("🗑")
        clr.setObjectName("ClearBtn")
        clr.setToolTip("Clear chat")
        clr.clicked.connect(self._clear_chat)
        row.addWidget(self.inp, stretch=4)
        row.addWidget(self.sbtn, stretch=1)
        row.addWidget(clr)
        lay.addLayout(row)

    # ── Bot ──

    def _init_bot(self):
        self.bot = None
        try:
            self.bot = GeminiBot(self.language)
        except Exception:
            if hasattr(self, "chat"):
                t = TM.t()
                self.chat.setHtml(
                    f'<center style="margin-top:40px">'
                    f'<span style="color:{t["dim"]};font-size:13px;">'
                    f'⚙  Add your Gemini API key in Settings to start.'
                    f'</span></center>'
                )

    # ── System Tray ──

    def _setup_tray(self):
        icon_p = _icon_path("arch-chan_mini.png")
        tray_icon = QIcon(icon_p) if icon_p else QApplication.instance().style().standardIcon(
            QApplication.instance().style().StandardPixmap.SP_ComputerIcon)

        self._tray = QSystemTrayIcon(tray_icon, self)
        self._tray.setToolTip("Linux Chan AI")

        menu = QMenu()
        show_act = QAction("Show / Hide", self)
        show_act.triggered.connect(self._toggle_visibility)
        quit_act = QAction("Quit", self)
        quit_act.triggered.connect(QApplication.instance().quit)
        menu.addAction(show_act)
        menu.addSeparator()
        menu.addAction(quit_act)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.messageClicked.connect(self._on_notif_clicked)
        self._tray.show()

    def _toggle_visibility(self):
        if self.isVisible():
            self.hide()
        else:
            self._last_interaction = time.time()
            self._notif_count = 0
            self.show()
            self.raise_()
            self.activateWindow()

    def _check_inactivity(self):
        if self.isVisible() or not self.bot:
            return
        if self._nworker and self._nworker.isRunning():
            return
        if self._notif_count >= len(NOTIF_SCHEDULE):
            return
        elapsed = time.time() - self._last_interaction
        if elapsed >= NOTIF_SCHEDULE[self._notif_count]:
            level = self._notif_count + 1
            self._notif_count += 1
            self._nworker = NotifWorker(self.bot, level)
            self._nworker.ready.connect(self._show_notif)
            self._nworker.start()

    def _check_sysmon(self):
        if not self.bot:
            return
        if self._sysmon_worker and self._sysmon_worker.isRunning():
            return
        if time.time() - self._last_sys_alert < SYS_ALERT_COOLDOWN:
            return
        self._sysmon_worker = SysMonWorker(self.bot)
        self._sysmon_worker.alert.connect(self._on_sys_alert)
        self._sysmon_worker.start()

    def _on_sys_alert(self, msg: str):
        self._last_sys_alert = time.time()
        self._push_notification("Linux Chan AI — System", msg, urgency="critical")
        if hasattr(self, "chat"):
            t = TM.t()
            pers = PERSONALITIES.get(cfg.get("personality"), next(iter(PERSONALITIES.values())))
            name = pers["name"]
            self.chat.append(
                f'<b style="color:#f59e0b">[System]</b> '
                f'<b style="color:{t["msg"]}">{name}:</b> '
                f'<span style="color:{t["text"]}">{msg}</span><br>'
            )
            sb = self.chat.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _on_notif_enabled(self, enabled: bool):
        if enabled:
            self._notif_count = 0
            self._notif_timer.start()
            self._sysmon_timer.start()
        else:
            self._notif_timer.stop()
            self._sysmon_timer.stop()

    def _push_notification(self, title: str, msg: str, urgency: str = "normal"):
        icon_p = _icon_path("arch-chan_mini.png")
        try:
            cmd = ["notify-send", "-a", "Linux Chan AI", "-u", urgency, "-t", "10000"]
            if icon_p:
                cmd += ["-i", icon_p]
            cmd += [title, msg]
            sub.Popen(cmd, stdout=sub.DEVNULL, stderr=sub.DEVNULL)
        except FileNotFoundError:
            self._tray.showMessage(title, msg, QSystemTrayIcon.MessageIcon.Information, 10000)

    def _show_notif(self, msg: str):
        self._push_notification("Linux Chan AI", msg)
        if hasattr(self, "chat"):
            t = TM.t()
            pers = PERSONALITIES.get(cfg.get("personality"), next(iter(PERSONALITIES.values())))
            name = pers["name"]
            chat_msg = (
                f'<b style="color:{t["msg"]}">{name}:</b> '
                f'<span style="color:{t["text"]}">{msg}</span>'
            )
            self.chat.append(chat_msg + "<br>")
            sb = self.chat.verticalScrollBar()
            sb.setValue(sb.maximum())

    def _on_notif_clicked(self):
        self._last_interaction = time.time()
        self._notif_count = 0
        self.show()
        self.raise_()
        self.activateWindow()
        self._nav(0)

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._toggle_visibility()

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self._tray.showMessage(
            "Linux Chan AI",
            "Running in the background. Right-click tray icon to quit.",
            QSystemTrayIcon.MessageIcon.Information,
            2000,
        )

    # ── Slots ──

    def _on_lang(self, lang: str):
        self.language = lang
        if self.bot:
            self.bot.language = lang
        if hasattr(self, "inp"):
            self.inp.setPlaceholderText(PLACEHOLDER.get(lang, "Type..."))
        if hasattr(self, "sbtn"):
            self.sbtn.setText(SEND_TXT.get(lang, "Send"))

    def _on_pers(self, p: str):
        if self.bot:
            self.bot.personality = p

    def _make_approval_box(self) -> QWidget:
        box = SectionBox()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(6)
        header = QLabel("Command requires approval:")
        header.setObjectName("FLbl")
        lay.addWidget(header)
        self._cmd_label = QLabel()
        self._cmd_label.setObjectName("FLbl")
        self._cmd_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._cmd_label.setStyleSheet(
            "font-family: 'Consolas','Ubuntu Mono',monospace; font-size: 12px;"
        )
        lay.addWidget(self._cmd_label)
        self._cmd_desc_label = QLabel()
        self._cmd_desc_label.setObjectName("Hint")
        self._cmd_desc_label.setWordWrap(True)
        lay.addWidget(self._cmd_desc_label)
        btn_row = QHBoxLayout()
        self._approve_btn = QPushButton("✓  Run Command")
        self._approve_btn.setObjectName("ApproveBtn")
        self._approve_btn.setFixedHeight(34)
        self._approve_btn.clicked.connect(self._approve_command)
        self._reject_btn = QPushButton("✕  Cancel")
        self._reject_btn.setObjectName("RejectBtn")
        self._reject_btn.setFixedHeight(34)
        self._reject_btn.clicked.connect(self._reject_command)
        btn_row.addWidget(self._approve_btn)
        btn_row.addWidget(self._reject_btn)
        btn_row.addStretch()
        lay.addLayout(btn_row)
        return box

    def _approve_command(self):
        self._approval_box.hide()
        cmd = self._pending_cmd
        self._pending_cmd = None
        if not cmd:
            self.sbtn.setEnabled(True)
            return
        self._approve_btn.setEnabled(False)
        self._reject_btn.setEnabled(False)
        self._exec_worker = CmdExecWorker(cmd)
        self._exec_worker.done.connect(self._on_cmd_done)
        self._exec_worker.start()

    def _on_cmd_done(self, cmd: str, out: str):
        t = TM.t()
        msg = (
            f'<span style="color:{t["accent"]}">$ {cmd}</span><br>'
            f'<span style="color:{t["dim"]}">{out}</span>'
        )
        self.chat.append(msg + "<br>")
        sb = self.chat.verticalScrollBar()
        sb.setValue(sb.maximum())
        self._char.set_state("linux")
        self._approve_btn.setEnabled(True)
        self._reject_btn.setEnabled(True)
        self.sbtn.setEnabled(True)

    def _reject_command(self):
        self._approval_box.hide()
        self._pending_cmd = None
        t = TM.t()
        self.chat.append(f'<span style="color:{t["dim"]}">Command cancelled.</span><br>')
        self._char.set_state("chat")
        self.sbtn.setEnabled(True)

    def _clear_chat(self):
        self.chat.clear()
        if self.bot:
            self.bot.clear_history()
        self._approval_box.hide()
        self._pending_cmd = None
        self._char.set_state("default")
        self.sbtn.setEnabled(True)

    def _on_layout(self, mode: str):
        if mode == self.layout_mode:
            return
        self.layout_mode = mode
        w, h = self.SIZES[mode]
        self.setFixedSize(w, h)
        self._root.setGeometry(0, 0, w, h)
        self._build_chat()

    # ── Chat ──

    def _send(self):
        if not self.bot:
            self._init_bot()
        if not self.bot:
            self.chat.append('<span style="color:#ef4444">Set API key in Settings first.</span><br>')
            return
        text = self.inp.text().strip()
        if not text:
            return
        self.sbtn.setEnabled(False)
        self.inp.clear()
        t = TM.t()
        self.chat.append(f'<span style="color:{t["dim"]}">You: {text}</span><br>')
        _pers = PERSONALITIES.get(cfg.get("personality"), next(iter(PERSONALITIES.values())))
        self._char.set_state(_pers.get("idle_state", "thinking"))
        self._last_interaction = time.time()
        self._notif_count = 0
        agent = pick_agent(text)
        self._worker = ChatWorker(self.bot, agent, text)
        self._worker.done.connect(self._on_resp)
        self._worker.error.connect(self._on_err)
        self._worker.start()

    def _on_resp(self, result):
        agent, resp = result
        t = TM.t()
        pers = PERSONALITIES.get(cfg.get("personality"), next(iter(PERSONALITIES.values())))
        name = pers["name"]

        if agent == "linux_command":
            cmd, desc = resp
            msg = (
                f'<b style="color:{t["msg"]}">{name}:</b> '
                f'<span style="color:{t["text"]}">{desc}</span>'
            )
            self.chat.append(msg + "<br>")
            sb = self.chat.verticalScrollBar()
            sb.setValue(sb.maximum())
            self._char.set_state(pers.get("idle_state", "thinking"))
            self._cmd_label.setText(f"$ {cmd}")
            self._cmd_desc_label.setText(desc)
            self._pending_cmd = cmd
            self._approval_box.show()
        elif agent == "file_operation":
            result, desc = resp
            t = TM.t()
            header = (
                f'<b style="color:{t["msg"]}">{name}:</b> '
                f'<span style="color:{t["text"]}">{desc}</span><br>'
            ) if desc else ""
            output = (
                f'<span style="color:{t["dim"]}; font-family: monospace; '
                f'white-space: pre;">{result}</span>'
            )
            self.chat.append(header + output + "<br>")
            sb = self.chat.verticalScrollBar()
            sb.setValue(sb.maximum())
            self._char.set_state("chat")
            self.sbtn.setEnabled(True)
        else:
            text, state = resp
            msg = (
                f'<b style="color:{t["msg"]}">{name}:</b> '
                f'<span style="color:{t["text"]}">{text}</span>'
            )
            self.chat.append(msg + "<br>")
            sb = self.chat.verticalScrollBar()
            sb.setValue(sb.maximum())
            self._char.set_state(state)

            if self.voice and isinstance(text, str):
                self._vworker = VoiceWorker(text, self.language)
                self._vworker.start()

            self.sbtn.setEnabled(True)

    def _on_err(self, err: str):
        msg = self._friendly_error(err)
        t = TM.t()
        self.chat.append(
            f'<span style="color:#ef4444;font-weight:bold">⚠ {msg}</span><br>'
        )
        self._char.set_state("error")
        self.sbtn.setEnabled(True)

    @staticmethod
    def _friendly_error(raw: str) -> str:
        r = raw.lower()
        if "429" in raw or "resource_exhausted" in r or "quota" in r:
            return "API quota reached — you've hit the rate limit. Wait a moment and try again."
        if "401" in raw or "api_key" in r or "invalid" in r and "key" in r:
            return "Invalid API key — check your Gemini API key in Settings."
        if "403" in raw or "permission" in r:
            return "Access denied — your API key may not have permission for this model."
        if "503" in raw or "unavailable" in r or "overloaded" in r:
            return "Gemini is temporarily overloaded — try again in a few seconds."
        if "timeout" in r:
            return "Request timed out — check your internet connection."
        if "api key not set" in r:
            return "No API key set — add your Gemini API key in Settings."
        return f"Something went wrong: {raw[:120]}"


# ── Entry ──────────────────────────────────────────────────────────────────────

def _cloud_notice(parent=None) -> None:
    """Tell the user, once, that this app talks to Google.

    Linux Chan has no local backend: every message, and every file or screen
    it reads for you, is sent to Gemini. On a distribution that promises
    nothing leaves the machine by default, that has to be said out loud rather
    than buried in a README.
    """
    if cfg.get("cloud_notice_ack"):
        return
    QMessageBox.information(
        parent,
        "Linux Chan uses Google Gemini",
        "Linux Chan has no offline mode. Everything you type, and the contents "
        "of any file or screenshot you ask her to read, is sent to Google's "
        "servers and handled under Google's terms.\n\n"
        "For a fully local assistant on this machine, use Maze AI, which runs "
        "models through Ollama and sends nothing anywhere.",
    )
    cfg.set("cloud_notice_ack", True)
    try:
        cfg.save()
    except Exception:
        pass


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setStyleSheet(make_stylesheet())

    p = _icon_path("arch-chan_mini.png")
    if p:
        app.setWindowIcon(QIcon(p))

    win = MainWindow()
    win.show()
    _cloud_notice(win)
    sys.exit(app.exec())
