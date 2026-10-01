"""
incident_response.py
============================================================
Incident Response Simulator
============================================================
Combines ALL SIX roadmap items into a single application:

    1. PROPER TOOL GUI (all options) -> MainApplication (sidebar nav)
    2. AI-DRIVEN SCENARIO GENERATION -> ScenarioGenerator, ScenarioGeneratorFrame
    3. GAMIFICATION                  -> GamificationEngine, GamifiedChallengeFrame
    4. LIVE INCIDENT EMULATION +
       COLLABORATION MODE            -> IncidentBroadcaster, CollaborationFrame
    5. CHATBOT ASSISTANT             -> ChatbotAssistantFrame
    6. METRICS DASHBOARD (MTTD/MTTR) -> MetricsTracker, MetricsDashboardFrame

Also implements the project's "Run using Administrator Access"
requirement: on Windows, launching this script (or double-clicking it)
triggers a UAC elevation prompt automatically via ensure_admin(), so
the tool always runs elevated — same as running VS Code/Sublime as
Administrator.

Run this file directly to launch the full app with all six features
behind a sidebar-navigation GUI (see MainApplication / __main__):

    python incident_response.py

Requirements:
    pip install ttkbootstrap matplotlib
============================================================
"""

import ctypes
import json
import os
import queue
import random
import socket
import sys
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Callable, Optional

import tkinter as tk
from tkinter import ttk
import ttkbootstrap as tb
from ttkbootstrap.constants import *


# ============================================================
# SECTION 0 — RUN AS ADMINISTRATOR
# Matches the project requirement: "Tools (Run using Administrator
# Access)". On Windows this re-launches the script elevated via UAC
# if it isn't already. On macOS/Linux it just warns (there's no
# single equivalent of UAC — normally you'd `sudo python3 ...`).
# ============================================================

def _is_admin_windows() -> bool:
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def ensure_admin():
    """
    Ensures this script is running with elevated (Administrator)
    privileges. If not, it relaunches itself elevated and exits the
    current unprivileged process. Call this as the very first thing
    in __main__, before creating any Tk windows.
    """
    if os.name != "nt":
        # No UAC equivalent to auto-elevate cross-platform without
        # extra dependencies. Just make the requirement visible.
        if os.geteuid() != 0:  # type: ignore[attr-defined]
            print("⚠️  This tool is intended to run with elevated privileges.")
            print("    Re-run it with: sudo python3 incident_response.py")
        return

    if _is_admin_windows():
        return  # already elevated, nothing to do

    # Not elevated yet -> relaunch this script with the 'runas' verb,
    # which triggers the standard Windows UAC elevation prompt.
    script = os.path.abspath(sys.argv[0])
    params = " ".join(f'"{arg}"' for arg in sys.argv[1:])
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", sys.executable, f'"{script}" {params}', None, 1
        )
        # ShellExecuteW returns a value > 32 on success
        if int(ret) <= 32:
            print("⚠️  Administrator elevation was cancelled or failed "
                  "(UAC prompt declined). Continuing without admin rights.")
            return
    except Exception as e:
        print(f"⚠️  Could not request Administrator elevation: {e}")
        return

    # The elevated child process is now launching separately —
    # exit this original, non-elevated process.
    sys.exit(0)

try:
    from ttkbootstrap.widgets import Meter
except ImportError:
    Meter = None

import matplotlib
matplotlib.use("Agg")  # backend is swapped to TkAgg implicitly when embedded via FigureCanvasTkAgg
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg

try:
    from PIL import Image, ImageDraw
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

try:
    import paho.mqtt.client as mqtt
    PAHO_AVAILABLE = True
except ImportError:
    PAHO_AVAILABLE = False


# ============================================================
# LOGO & ICON — generated once, saved to disk, and set as the
# real application/taskbar icon (not just a page decoration).
# ============================================================

ASSETS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
ICON_ICO_PATH = os.path.join(ASSETS_DIR, "icon.ico")
ICON_PNG_PATH = os.path.join(ASSETS_DIR, "icon.png")

SHIELD_BLUE = (63, 167, 214, 255)
SHIELD_OUTLINE = (22, 74, 97, 255)
SHIELD_CHECK = (240, 248, 255, 255)


def _draw_shield(size: int) -> "Image.Image":
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    m = size * 0.06  # margin
    points = [
        (size * 0.5, m),
        (size - m, size * 0.24),
        (size - m, size * 0.56),
        (size * 0.5, size - m),
        (m, size * 0.56),
        (m, size * 0.24),
    ]
    outline_w = max(1, round(size * 0.03))
    draw.polygon(points, fill=SHIELD_BLUE, outline=SHIELD_OUTLINE)
    for i in range(outline_w):
        draw.polygon(points, outline=SHIELD_OUTLINE)

    # checkmark, drawn as two thick line segments
    lw = max(2, round(size * 0.07))
    cx, cy = size * 0.5, size * 0.5
    draw.line([(cx - size * 0.18, cy), (cx - size * 0.04, cy + size * 0.14)],
              fill=SHIELD_CHECK, width=lw, joint="curve")
    draw.line([(cx - size * 0.04, cy + size * 0.14), (cx + size * 0.22, cy - size * 0.16)],
              fill=SHIELD_CHECK, width=lw, joint="curve")
    return img


def generate_logo_icon():
    """Generates the tool's logo/icon once and saves it under ./assets/
    (icon.ico for Windows taskbar/title bar, icon.png for cross-platform
    use). Safe to call repeatedly — skips regeneration if files already
    exist. Returns (ico_path, png_path), or (None, None) if PIL isn't
    available (the app still runs fine without it — it just falls back
    to a plain drawn placeholder on the Project Info page)."""
    if not PIL_AVAILABLE:
        return None, None
    os.makedirs(ASSETS_DIR, exist_ok=True)
    if not os.path.exists(ICON_PNG_PATH):
        _draw_shield(256).save(ICON_PNG_PATH)
    if not os.path.exists(ICON_ICO_PATH):
        _draw_shield(256).save(
            ICON_ICO_PATH,
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
        )
    return ICON_ICO_PATH, ICON_PNG_PATH


# ============================================================
# SECTION 1 — GAMIFICATION
# (XP, levels, badges, streaks, leaderboard + one full
#  gamified scenario: "Incident Response Challenge", self-paced)
# ============================================================

LEADERBOARD_FILE = "leaderboard.json"

LEVEL_THRESHOLDS = [0, 100, 250, 450, 700, 1000, 1400, 1900, 2500, 3200, 4000]

BADGES = {
    "first_blood":      {"label": "First Response",  "desc": "Completed your first scenario",         "icon": "🥇"},
    "perfect_streak_5":  {"label": "5-Streak",         "desc": "5 correct answers in a row",            "icon": "🔥"},
    "perfect_streak_10": {"label": "10-Streak",        "desc": "10 correct answers in a row",           "icon": "🔥🔥"},
    "level_5":           {"label": "Seasoned Analyst", "desc": "Reached Level 5",                       "icon": "🛡️"},
    "level_10":          {"label": "IR Veteran",       "desc": "Reached Level 10",                      "icon": "🏆"},
    "flawless_round":    {"label": "Flawless Round",   "desc": "Completed a challenge with 0 mistakes", "icon": "💎"},
}


@dataclass
class TraineeProgress:
    name: str
    emp_id: str
    xp: int = 0
    level: int = 1
    streak: int = 0
    best_streak: int = 0
    badges: list = field(default_factory=list)
    scenarios_completed: int = 0
    correct_answers: int = 0
    wrong_answers: int = 0


class GamificationEngine:
    """Owns XP math, badge unlocking, and JSON leaderboard persistence."""

    def __init__(self, trainee_name: str, emp_id: str, storage_path: str = LEADERBOARD_FILE):
        self.storage_path = storage_path
        self.board = self._load()
        key = self._key(trainee_name, emp_id)
        if key not in self.board:
            self.board[key] = asdict(TraineeProgress(name=trainee_name, emp_id=emp_id))
        self.key = key

    def _key(self, name, emp_id):
        return f"{emp_id}:{name}"

    def _load(self) -> dict:
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save(self):
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self.board, f, indent=2)

    @property
    def progress(self) -> dict:
        return self.board[self.key]

    def award(self, correct: bool) -> dict:
        """Awards XP for an answer. No timing/speed component — self-paced."""
        p = self.progress
        result = {"xp_gained": 0, "level_up": False, "new_badges": [], "correct": correct}

        if correct:
            gained = 25  # fixed XP per correct answer (untimed)
            p["xp"] += gained
            p["correct_answers"] += 1
            p["streak"] += 1
            p["best_streak"] = max(p["best_streak"], p["streak"])
            result["xp_gained"] = gained

            if p["streak"] == 5:
                self._unlock(p, "perfect_streak_5", result)
            if p["streak"] == 10:
                self._unlock(p, "perfect_streak_10", result)
        else:
            p["wrong_answers"] += 1
            p["streak"] = 0

        new_level = self._level_for_xp(p["xp"])
        if new_level > p["level"]:
            p["level"] = new_level
            result["level_up"] = True
            if new_level >= 5:
                self._unlock(p, "level_5", result)
            if new_level >= 10:
                self._unlock(p, "level_10", result)

        self._save()
        return result

    def complete_scenario(self, flawless: bool):
        p = self.progress
        p["scenarios_completed"] += 1
        if p["scenarios_completed"] == 1:
            fake = {"new_badges": []}
            self._unlock(p, "first_blood", fake)
        if flawless:
            fake = {"new_badges": []}
            self._unlock(p, "flawless_round", fake)
        self._save()

    def _unlock(self, p, badge_key, result):
        if badge_key not in p["badges"]:
            p["badges"].append(badge_key)
            result["new_badges"].append(BADGES[badge_key])

    def _level_for_xp(self, xp: int) -> int:
        level = 1
        for i, threshold in enumerate(LEVEL_THRESHOLDS, start=1):
            if xp >= threshold:
                level = i
        return level

    def xp_to_next_level(self):
        p = self.progress
        cur_level = p["level"]
        if cur_level >= len(LEVEL_THRESHOLDS):
            return p["xp"], 0, 1.0
        next_threshold = LEVEL_THRESHOLDS[cur_level]
        prev_threshold = LEVEL_THRESHOLDS[cur_level - 1]
        span = max(1, next_threshold - prev_threshold)
        progress_ratio = (p["xp"] - prev_threshold) / span
        return p["xp"], next_threshold, min(1.0, max(0.0, progress_ratio))

    def leaderboard(self, top_n: int = 10):
        rows = list(self.board.values())
        rows.sort(key=lambda r: r["xp"], reverse=True)
        return rows[:top_n]


GAMIFIED_SCENARIO = {
    "title": "🛡️ Incident Response Challenge",
    "intro": (
        "A ransomware strain is actively encrypting files on a file server, and more "
        "scenarios follow after that. Take your time on each one — there's no countdown. "
        "Use ◀ Previous / Next ▶ to move between questions. Wrong answers break your streak."
    ),
    "questions": [
        {
            "situation": "Encryption activity detected on FS-03. Ransom note dropped in shared drive.",
            "options": {
                "A": "Immediately power off the affected server.",
                "B": "Isolate FS-03 from the network (disable NIC/segment), preserve state, then begin forensics.",
                "C": "Pay the ransom to stop encryption quickly.",
            },
            "correct": "B",
            "feedback": {
                "A": "Powering off can destroy volatile memory evidence needed for forensics.",
                "B": "Correct — isolate first to stop spread while preserving evidence.",
                "C": "Paying is a last resort and doesn't guarantee decryption; not the first move.",
            },
        },
        {
            "situation": "You've isolated FS-03. Backups exist but their last verified restore test was 8 months ago.",
            "options": {
                "A": "Assume backups are fine and start mass restore immediately.",
                "B": "Verify backup integrity and check for reinfection vectors before restoring.",
                "C": "Skip backups entirely and rebuild the server from scratch with no data.",
            },
            "correct": "B",
            "feedback": {
                "A": "Untested backups may be corrupted or already compromised — verify first.",
                "B": "Correct — validate integrity and close the infection vector before restoring.",
                "C": "Unnecessarily destructive when good backups may still be usable.",
            },
        },
        {
            "situation": "Legal and PR are asking whether this needs to be disclosed to regulators.",
            "options": {
                "A": "Decide alone as the IR lead — no need to involve legal.",
                "B": "Escalate to legal/compliance to assess breach notification obligations (e.g., contains PII).",
                "C": "Wait until the investigation fully closes before telling anyone outside IT.",
            },
            "correct": "B",
            "feedback": {
                "A": "Disclosure obligations are legal/compliance decisions, not solely IR's call.",
                "B": "Correct — loop in legal/compliance early; many regulations have strict notification windows.",
                "C": "Delaying too long can itself create legal exposure under breach-notification laws.",
            },
        },
        {
            "situation": "A login form starts returning database errors after a user enters a single quote (') in the username field.",
            "options": {
                "A": "Ignore it — error messages aren't a real security issue.",
                "B": "Treat it as a likely SQL Injection flaw; sanitize input and switch to parameterized queries.",
                "C": "Just hide the error message from the user and move on.",
            },
            "correct": "B",
            "feedback": {
                "A": "Verbose SQL errors from a single quote are a classic SQL Injection indicator — never ignore it.",
                "B": "Correct — this is textbook SQL Injection; fix the root cause with parameterized queries.",
                "C": "Hiding the error doesn't fix the underlying injectable query — the vulnerability remains.",
            },
        },
        {
            "situation": "A support page reflects a URL parameter directly into the page without encoding, and a tester submits a <script> payload that executes.",
            "options": {
                "A": "Escape/encode all user-supplied output and apply a Content Security Policy (XSS fix).",
                "B": "Block the tester's IP address and consider the issue closed.",
                "C": "Do nothing since it only affects that one page.",
            },
            "correct": "A",
            "feedback": {
                "A": "Correct — output encoding plus CSP is the standard defense against reflected/stored XSS.",
                "B": "Blocking one tester doesn't fix the vulnerability for real attackers.",
                "C": "Unpatched XSS can be used to hijack sessions or steal credentials from any visitor.",
            },
        },
        {
            "situation": "Network monitoring shows a sudden 50x spike in inbound traffic from thousands of distinct IPs, and the web server is becoming unresponsive.",
            "options": {
                "A": "Reboot the web server repeatedly until traffic normalizes.",
                "B": "Engage upstream DDoS mitigation (ISP/CDN/scrubbing) and enable rate limiting.",
                "C": "Increase server RAM and hope it absorbs the load.",
            },
            "correct": "B",
            "feedback": {
                "A": "Rebooting does nothing against sustained volumetric traffic — it will just go down again.",
                "B": "Correct — volumetric DDoS needs upstream mitigation; local hardware can't out-scale it alone.",
                "C": "More RAM won't help against a true volumetric flood; the bottleneck is network bandwidth.",
            },
        },
        {
            "situation": "Internal DNS queries for your banking portal are silently resolving to an unfamiliar external IP address.",
            "options": {
                "A": "Assume it's a temporary glitch and check again tomorrow.",
                "B": "Investigate for DNS spoofing/cache poisoning, verify DNSSEC, and flush/lock down resolver configs.",
                "C": "Change the banking portal's domain name to avoid the issue.",
            },
            "correct": "B",
            "feedback": {
                "A": "DNS resolving to an unexpected IP for a sensitive domain should never be dismissed as a glitch.",
                "B": "Correct — this is a classic DNS spoofing pattern; validate DNSSEC and lock down resolver trust.",
                "C": "Renaming the domain doesn't address a poisoned resolver or cache — the root cause remains.",
            },
        },
        {
            "situation": "Antivirus flags identical malware signatures spreading rapidly across multiple workstations on the same subnet within minutes.",
            "options": {
                "A": "Let antivirus handle it automatically with no further action.",
                "B": "Segment the affected subnet, patch the exploited vulnerability, and hunt for the worm's propagation method.",
                "C": "Only clean the first infected machine you find.",
            },
            "correct": "B",
            "feedback": {
                "A": "Self-propagating worms often outrun antivirus signature updates — active containment is required.",
                "B": "Correct — network segmentation plus patching the exploited flaw stops worm propagation at its source.",
                "C": "Cleaning one machine does nothing to stop the worm from re-infecting it from its neighbors.",
            },
        },
        {
            "situation": "An employee reports an email from 'IT-Support' urgently asking them to click a link and re-enter their password within 10 minutes or lose access.",
            "options": {
                "A": "Reply directly to the email asking if it's legitimate.",
                "B": "Don't click; verify independently via a known IT contact/channel, then report and quarantine the email.",
                "C": "Forward it to coworkers so they can decide for themselves.",
            },
            "correct": "B",
            "feedback": {
                "A": "Replying to the suspicious sender confirms your address is active and may leak more information.",
                "B": "Correct — urgency + credential requests are classic phishing; verify out-of-band and report it.",
                "C": "Forwarding spreads a potential phishing attempt instead of containing it.",
            },
        },
        {
            "situation": "A caller claiming to be from the helpdesk asks an employee to read out their MFA one-time code to 'verify their identity.'",
            "options": {
                "A": "Read the code — the caller sounded confident and knew the employee's name.",
                "B": "Refuse, hang up, and independently verify through the official IT helpdesk number (vishing).",
                "C": "Give a fake code to see what the caller does.",
            },
            "correct": "B",
            "feedback": {
                "A": "Legitimate IT staff never need your MFA code — this is a textbook vishing attack.",
                "B": "Correct — never share MFA codes over the phone; verify independently through official channels.",
                "C": "Engaging with a suspected attacker, even playfully, risks revealing useful information.",
            },
        },
        {
            "situation": "A finance employee gets a highly personalized email referencing a real vendor invoice, asking them to update banking details for payment.",
            "options": {
                "A": "Update the banking details since the email seems well-informed.",
                "B": "Verify the change request by calling the vendor directly using a previously known phone number (spear phishing).",
                "C": "Forward the request to the vendor's email address for confirmation.",
            },
            "correct": "B",
            "feedback": {
                "A": "Personalization is often gathered via reconnaissance — it doesn't prove legitimacy; this is spear phishing.",
                "B": "Correct — always verify payment/banking changes via an independently known phone number.",
                "C": "Replying to the same (possibly spoofed) email channel doesn't verify anything.",
            },
        },
        {
            "situation": "A vendor technician arrives without an appointment, claiming to need 'quick access' to a secure server room to fix an urgent issue.",
            "options": {
                "A": "Let them in immediately since delays could make the urgent issue worse.",
                "B": "Verify their identity and appointment through your access-control process before granting entry (social engineering).",
                "C": "Give them a badge and let them work unsupervised.",
            },
            "correct": "B",
            "feedback": {
                "A": "Urgency and unannounced visits are common social engineering tactics — always verify first.",
                "B": "Correct — physical access requests must go through proper verification regardless of urgency.",
                "C": "Unsupervised physical access for an unverified person creates serious security risk.",
            },
        },
        {
            "situation": "Unusual after-hours database queries are traced back to a privileged account belonging to a disgruntled employee serving their notice period.",
            "options": {
                "A": "Confront the employee directly and ask them to stop.",
                "B": "Involve HR/legal, review access logs, and restrict/revoke access following proper offboarding procedure.",
                "C": "Wait until their last day to review what happened.",
            },
            "correct": "B",
            "feedback": {
                "A": "Confronting directly can tip off the individual and risks destruction of evidence or retaliation.",
                "B": "Correct — insider threat cases need HR/legal involvement and careful, documented access review.",
                "C": "Waiting allows continued unauthorized access and potential further data loss.",
            },
        },
        {
            "situation": "Large volumes of customer data are found being uploaded to an unfamiliar external cloud storage account from an internal workstation.",
            "options": {
                "A": "Delete the uploaded files from the external account remotely.",
                "B": "Isolate the workstation, preserve logs/evidence, and investigate the scope of exfiltration before deciding next steps.",
                "C": "Wait a few days to see if more data gets uploaded before acting.",
            },
            "correct": "B",
            "feedback": {
                "A": "You may not have authorization or ability to alter external accounts, and this could destroy evidence.",
                "B": "Correct — contain first, preserve evidence, then scope the exfiltration before remediation.",
                "C": "Waiting allows the exfiltration to continue and increases the scope of the breach.",
            },
        },
    ],
}


class GamifiedChallengeFrame(tb.Frame):
    """A self-paced, scored, badge-earning scenario frame with back/forward navigation.

    No countdown/timer — the trainee can take as long as they like on each
    question, and can move back to review previously-answered questions or
    forward again, using the ◀ Previous / Next ▶ buttons.
    """

    def __init__(self, master, engine: GamificationEngine,
                 scenario: dict = None, on_complete: Optional[Callable] = None,
                 metrics_tracker: "MetricsTracker" = None):
        super().__init__(master, padding=20)
        self.engine = engine
        self.scenario = scenario or GAMIFIED_SCENARIO
        self.on_complete = on_complete
        self.metrics_tracker = metrics_tracker

        self.q_index = 0
        self.mistakes = 0
        self.q_start_time = None
        # Per-question record of what's already been answered, so navigating
        # back and forth doesn't re-award XP or re-log metrics.
        # index -> {"chosen": "A"/"B"/"C"/None, "note": str}  (displayed letter)
        self.answers = {}
        # Per-question shuffled A/B/C order, so the correct answer isn't
        # always in the same position (e.g. always "B") across plays.
        # index -> {"A": orig_letter, "B": orig_letter, "C": orig_letter}
        self.option_maps = {}
        self.started = False

        self._build_header()
        self._build_body()
        self._show_intro()

    def _build_header(self):
        top = tb.Frame(self)
        top.pack(fill=X, pady=(0, 10))

        tb.Label(top, text=self.scenario["title"], font=("Segoe UI", 18, "bold"),
                  bootstyle="info").pack(side=LEFT)

        self.xp_label = tb.Label(top, text=self._xp_text(), font=("Segoe UI", 10),
                                   bootstyle="secondary")
        self.xp_label.pack(side=RIGHT)

        self.xp_bar = tb.Progressbar(self, bootstyle="success-striped", maximum=1.0)
        self.xp_bar.pack(fill=X, pady=(0, 15))
        self._refresh_xp_bar()

    def _build_body(self):
        self.body = tb.Frame(self)
        self.body.pack(fill=BOTH, expand=True)

    def _xp_text(self):
        p = self.engine.progress
        return (f"Lvl {p['level']}  |  {p['xp']} XP  |  🔥 Streak {p['streak']}  "
                f"(best {p['best_streak']})  |  Badges: {len(p['badges'])}")

    def _refresh_xp_bar(self):
        xp, next_threshold, ratio = self.engine.xp_to_next_level()
        self.xp_bar["value"] = ratio

    def _show_intro(self):
        self._clear_body()
        tb.Label(self.body, text=self.scenario["intro"], font=("Segoe UI", 11),
                  wraplength=700, justify=LEFT).pack(pady=20, anchor=W)
        tb.Button(self.body, text="Begin Challenge ▶", bootstyle="success",
                   command=self._start).pack(pady=10)

    def _start(self):
        self.started = True
        self.q_index = 0
        self._show_question(0)

    def _clear_body(self):
        for w in self.body.winfo_children():
            w.destroy()

    # ---------------- question rendering ----------------
    def _show_question(self, index: int):
        total = len(self.scenario["questions"])
        if index >= total:
            self._finish()
            return

        self.q_index = index
        q = self.scenario["questions"][index]
        self._clear_body()

        # Get (or create, on first view) a shuffled A/B/C -> original-letter
        # mapping for this question, so the correct answer's displayed
        # position varies instead of always landing on the same letter.
        if index not in self.option_maps:
            shuffled_orig = random.sample(["A", "B", "C"], 3)
            self.option_maps[index] = {"A": shuffled_orig[0], "B": shuffled_orig[1], "C": shuffled_orig[2]}
        opt_map = self.option_maps[index]  # displayed letter -> original letter

        tb.Label(self.body, text=f"Question {index + 1} of {total}",
                  bootstyle="secondary").pack(anchor=W)

        tb.Label(self.body, text=q["situation"], font=("Segoe UI", 13),
                  wraplength=700, justify=LEFT).pack(pady=(5, 15), anchor=W)

        self.answer_buttons = {}
        already = self.answers.get(index)  # None if not yet answered
        for key in ("A", "B", "C"):
            orig_key = opt_map[key]
            btn = tb.Button(self.body, text=f"{key}. {q['options'][orig_key]}",
                              bootstyle="outline-info", width=90,
                              command=lambda k=key: self._answer(k))
            btn.pack(fill=X, pady=4)
            self.answer_buttons[key] = btn

        self.feedback_label = tb.Label(self.body, text="", font=("Segoe UI", 10, "italic"),
                                         wraplength=700, justify=LEFT)
        self.feedback_label.pack(pady=(15, 0), anchor=W)

        # Navigation row (Previous / Next) — always available so trainees
        # can move freely between questions at their own pace.
        nav = tb.Frame(self.body)
        nav.pack(fill=X, pady=(20, 0))

        prev_btn = tb.Button(nav, text="◀ Previous", bootstyle="secondary-outline",
                               command=self._go_previous, state=(NORMAL if index > 0 else DISABLED))
        prev_btn.pack(side=LEFT)

        next_text = "Next ▶" if index < total - 1 else "Finish ▶"
        next_btn = tb.Button(nav, text=next_text, bootstyle="secondary-outline",
                               command=self._go_next,
                               state=(NORMAL if already is not None else DISABLED))
        next_btn.pack(side=RIGHT)
        self.next_btn = next_btn

        if already is not None:
            # Re-render this question's already-given answer/feedback.
            self._render_answered_state(q, already["chosen"], already["note"], index)
        else:
            self.q_start_time = time.time()

    def _render_answered_state(self, q, chosen, note, index):
        opt_map = self.option_maps[index]
        correct_key = next(k for k, orig in opt_map.items() if orig == q["correct"])
        for btn in self.answer_buttons.values():
            btn.config(state=DISABLED)
        if chosen and chosen != correct_key:
            self.answer_buttons[chosen].config(bootstyle="danger")
        self.answer_buttons[correct_key].config(bootstyle="success")
        self.feedback_label.config(text=note)

    # ---------------- navigation ----------------
    def _go_previous(self):
        if self.q_index > 0:
            self._show_question(self.q_index - 1)

    def _go_next(self):
        self._show_question(self.q_index + 1)

    # ---------------- answering ----------------
    def _answer(self, chosen):
        index = self.q_index
        if index in self.answers:
            return  # already answered this one — no re-scoring on revisit

        for btn in self.answer_buttons.values():
            btn.config(state=DISABLED)

        q = self.scenario["questions"][index]
        opt_map = self.option_maps[index]          # displayed letter -> original letter
        chosen_orig = opt_map[chosen]                # what the original A/B/C this maps to
        correct_key = next(k for k, orig in opt_map.items() if orig == q["correct"])
        is_correct = (chosen_orig == q["correct"])

        if not is_correct:
            self.mistakes += 1

        result = self.engine.award(is_correct)

        # Log a REAL incident record (elapsed time is just for the Metrics
        # Dashboard's MTTD/MTTR stats — there is no countdown or pressure).
        if self.metrics_tracker is not None:
            now = time.time()
            self.metrics_tracker.log_incident(
                scenario_name=q["situation"][:60],
                detected_at=self.q_start_time,
                responded_at=now,
                resolved=is_correct,
                resolved_at=now,
            )

        if chosen and chosen != correct_key:
            self.answer_buttons[chosen].config(bootstyle="danger")
        self.answer_buttons[correct_key].config(bootstyle="success")

        note = q["feedback"][chosen_orig]
        if result["xp_gained"]:
            note += f"\n+{result['xp_gained']} XP"
        if result["level_up"]:
            note += f"\n🎉 Level up! You're now Level {self.engine.progress['level']}."
        for b in result["new_badges"]:
            note += f"\n{b['icon']} Badge unlocked: {b['label']} — {b['desc']}"

        self.feedback_label.config(text=note)
        self.xp_label.config(text=self._xp_text())
        self._refresh_xp_bar()

        self.answers[index] = {"chosen": chosen, "note": note}
        self.next_btn.config(state=NORMAL)

    def _finish(self):
        flawless = (self.mistakes == 0)
        self.engine.complete_scenario(flawless)
        self._clear_body()

        msg = "🏁 Challenge complete!\n\n"
        msg += "💎 Flawless round — no mistakes!\n" if flawless else f"Mistakes made: {self.mistakes}\n"
        msg += f"\n{self._xp_text()}"

        tb.Label(self.body, text=msg, font=("Segoe UI", 13), justify=LEFT).pack(pady=20, anchor=W)

        board = self.engine.leaderboard()
        tb.Label(self.body, text="🏆 Leaderboard (Top 10)", font=("Segoe UI", 12, "bold")).pack(anchor=W, pady=(10, 5))
        for i, row in enumerate(board, start=1):
            tb.Label(self.body, text=f"{i}. {row['name']} ({row['emp_id']}) — {row['xp']} XP, Lvl {row['level']}",
                      font=("Segoe UI", 10)).pack(anchor=W)

        tb.Button(self.body, text="◀ Review Answers", bootstyle="secondary-outline",
                   command=lambda: self._show_question(len(self.scenario["questions"]) - 1)
                   ).pack(pady=(15, 0), anchor=W)

        if self.on_complete:
            self.on_complete(self.engine.progress)


# ============================================================
# SECTION 2 — METRICS DASHBOARD (MTTD & MTTR)
# ============================================================

HISTORY_FILE = "metrics_history.json"


@dataclass
class IncidentRecord:
    scenario_name: str
    detect_seconds: float
    resolve_seconds: float
    resolved_correctly: bool
    timestamp: float


class MetricsTracker:
    def __init__(self, storage_path: str = HISTORY_FILE):
        self.storage_path = storage_path
        self.records = self._load()

    def _load(self):
        if os.path.exists(self.storage_path):
            try:
                with open(self.storage_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                return []
        return []

    def _save(self):
        with open(self.storage_path, "w", encoding="utf-8") as f:
            json.dump(self.records, f, indent=2)

    def log_incident(self, scenario_name: str, detected_at: float, responded_at: float,
                      resolved: bool, resolved_at: float = None):
        detect_seconds = max(0.0, responded_at - detected_at)
        resolve_seconds = max(0.0, (resolved_at or responded_at) - detected_at)
        record = IncidentRecord(
            scenario_name=scenario_name,
            detect_seconds=round(detect_seconds, 2),
            resolve_seconds=round(resolve_seconds, 2),
            resolved_correctly=resolved,
            timestamp=time.time(),
        )
        self.records.append(asdict(record))
        self._save()

    def mttd(self) -> float:
        if not self.records:
            return 0.0
        return sum(r["detect_seconds"] for r in self.records) / len(self.records)

    def mttr(self) -> float:
        resolved = [r for r in self.records if r["resolved_correctly"]]
        if not resolved:
            return 0.0
        return sum(r["resolve_seconds"] for r in resolved) / len(resolved)

    def resolution_rate(self) -> float:
        if not self.records:
            return 0.0
        resolved = sum(1 for r in self.records if r["resolved_correctly"])
        return resolved / len(self.records)

    def recent(self, n: int = 8):
        return self.records[-n:]


class MetricsDashboardFrame(tb.Frame):
    """Dashboard with Meter gauges + trend chart + recent incident table."""

    def __init__(self, master, tracker: MetricsTracker):
        super().__init__(master, padding=20)
        self.tracker = tracker
        self._build()

    def _build(self):
        # Rebuilds all child widgets in place. NEVER call self.__init__()
        # again to "refresh" — re-invoking Frame.__init__ on a live widget
        # silently creates an orphaned duplicate Tk widget instead of
        # reusing this one, which is what caused the dashboard to appear
        # stuck/blank when switching to it.
        for w in self.winfo_children():
            w.destroy()

        tb.Label(self, text="📊 Metrics Dashboard — MTTD & MTTR",
                  font=("Segoe UI", 18, "bold"), bootstyle="info").pack(anchor=W, pady=(0, 15))

        self._build_gauges()
        self._build_chart()
        self._build_table()
        self._build_refresh()

    def _build_gauges(self):
        row = tb.Frame(self)
        row.pack(fill=X, pady=10)

        if Meter is not None:
            self.mttd_meter = Meter(
                row, metersize=180, amountused=round(self.tracker.mttd(), 1),
                amounttotal=max(60, round(self.tracker.mttd() * 1.5) or 60),
                metertype="semi", subtext="MTTD (sec)", bootstyle="warning",
                interactive=False,
            )
            self.mttd_meter.pack(side=LEFT, padx=20)

            self.mttr_meter = Meter(
                row, metersize=180, amountused=round(self.tracker.mttr(), 1),
                amounttotal=max(120, round(self.tracker.mttr() * 1.5) or 120),
                metertype="semi", subtext="MTTR (sec)", bootstyle="danger",
                interactive=False,
            )
            self.mttr_meter.pack(side=LEFT, padx=20)
        else:
            tb.Label(row, text=f"MTTD: {self.tracker.mttd():.1f}s   |   MTTR: {self.tracker.mttr():.1f}s",
                      font=("Segoe UI", 14)).pack()

        rate_pct = self.tracker.resolution_rate() * 100
        tb.Label(row, text=f"✅ Correct Resolution Rate\n{rate_pct:.0f}%",
                  font=("Segoe UI", 13, "bold"), justify=CENTER,
                  bootstyle="success").pack(side=LEFT, padx=30)

    def _build_chart(self):
        BG = "#222222"       # matches the app's darkly theme background
        FG = "#e6e6e6"       # light text/axis color, visible on dark bg
        GRID = "#3a3a3a"

        records = self.tracker.recent(10)
        fig, ax = plt.subplots(figsize=(7, 2.6), dpi=100)

        # Solid dark background instead of a transparent one — transparent
        # figures render as solid black when embedded in a Tk canvas.
        fig.patch.set_facecolor(BG)
        ax.set_facecolor(BG)

        if records:
            x = list(range(1, len(records) + 1))
            detect_vals = [r["detect_seconds"] for r in records]
            resolve_vals = [r["resolve_seconds"] for r in records]
            ax.plot(x, detect_vals, marker="o", label="Time to Detect", color="#f0ad4e")
            ax.plot(x, resolve_vals, marker="o", label="Time to Resolve", color="#e74c3c")
            ax.set_xticks(x)
            legend = ax.legend(loc="upper right", fontsize=8, facecolor=BG, edgecolor=GRID)
            for text in legend.get_texts():
                text.set_color(FG)
        else:
            ax.text(0.5, 0.5, "No incidents logged yet", ha="center", va="center", color=FG)

        ax.set_ylabel("Seconds", color=FG)
        ax.set_title("Recent Incident Trend (last 10)", fontsize=10, color=FG)
        ax.tick_params(colors=FG)
        ax.grid(True, color=GRID, linewidth=0.5)
        for spine in ax.spines.values():
            spine.set_color(GRID)
        fig.tight_layout()

        canvas = FigureCanvasTkAgg(fig, master=self)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=X, pady=15)
        plt.close(fig)

    def _build_table(self):
        tb.Label(self, text="Recent Incidents", font=("Segoe UI", 12, "bold")).pack(anchor=W, pady=(5, 5))

        cols = ("scenario", "detect", "resolve", "outcome")
        tree = tb.Treeview(self, columns=cols, show="headings", height=6, bootstyle="info")
        tree.heading("scenario", text="Scenario")
        tree.heading("detect", text="Detect (s)")
        tree.heading("resolve", text="Resolve (s)")
        tree.heading("outcome", text="Outcome")
        tree.column("scenario", width=320)
        tree.column("detect", width=90, anchor=CENTER)
        tree.column("resolve", width=90, anchor=CENTER)
        tree.column("outcome", width=100, anchor=CENTER)

        for r in reversed(self.tracker.recent(10)):
            outcome = "✅ Correct" if r["resolved_correctly"] else "❌ Missed"
            tree.insert("", END, values=(r["scenario_name"], r["detect_seconds"], r["resolve_seconds"], outcome))

        tree.pack(fill=X)

    def _build_refresh(self):
        tb.Button(self, text="🔄 Refresh Dashboard", bootstyle="secondary-outline",
                   command=self._refresh).pack(pady=15)

    def _refresh(self):
        self._build()


# ============================================================
# SECTION 3 — CHATBOT ASSISTANT
# ============================================================

BOT_NAME = "IR Buddy"

KNOWLEDGE_BASE = {
    "contain": (
        "Containment first, cleanup second. Isolate the affected host/segment "
        "(network disable, VLAN quarantine, disable account) before you start "
        "digging — this stops the bleeding without destroying evidence."
    ),
    "forensic": (
        "Preserve before you poke. Capture volatile memory and logs before "
        "powering anything off, and maintain a documented chain of custody "
        "for anything you collect."
    ),
    "chain of custody": (
        "Chain of custody = who touched the evidence, when, and why — documented "
        "end to end. Missing links can make evidence inadmissible later."
    ),
    "phishing": (
        "Red flags: mismatched sender domain, urgency/fear language, unexpected "
        "attachments or links, requests to bypass normal approval steps. When in "
        "doubt, verify out-of-band (call the person, don't reply to the email)."
    ),
    "ransomware": (
        "Isolate the infected host(s) immediately, preserve state for forensics, "
        "check backup integrity before restoring, and loop in legal/compliance "
        "before deciding on ransom payment — paying is a last resort, not step one."
    ),
    "ddos": (
        "For DDoS: engage upstream mitigation (ISP/CDN/scrubbing service), enable "
        "rate limiting, and keep stakeholders updated — don't try to 'out-scale' a "
        "large volumetric attack with your own infra alone."
    ),
    "sql injection": (
        "Root cause is almost always unsanitized input reaching a query. Patch with "
        "parameterized queries / prepared statements, then look for other endpoints "
        "with the same pattern — one instance rarely means the only instance."
    ),
    "insider threat": (
        "Handle insider cases carefully: involve HR and legal early, don't tip off "
        "the individual prematurely, and preserve access logs before revoking "
        "credentials so you don't lose the audit trail."
    ),
    "disclos": (
        "Breach notification obligations depend on data type and jurisdiction (e.g. "
        "PII, health data). This is a joint call with legal/compliance, not an IT-only "
        "decision, and many regulations have strict notification windows."
    ),
    "mttd": (
        "MTTD = Mean Time To Detect — how long between an incident starting and your "
        "team noticing it. Lower is better; it reflects monitoring/alerting maturity."
    ),
    "mttr": (
        "MTTR = Mean Time To Resolve — how long between detection and full resolution. "
        "Lower is better; it reflects how efficient your response process is."
    ),
    "score": (
        "Scoring rewards both correctness and speed in gamified challenges — quick "
        "correct answers earn a speed bonus, and consecutive correct answers build a streak."
    ),
    "badge": (
        "Badges unlock automatically as you play: your first completed scenario, fast "
        "answers, streaks, level milestones, and flawless (zero-mistake) rounds."
    ),
    "hint": (
        "Try the 'Hint for this scenario' button below — I'll tailor a nudge to whatever "
        "situation is currently on your screen."
    ),
}

FALLBACK_REPLIES = [
    "I'm not sure about that one yet — try asking about containment, forensics, phishing, "
    "ransomware, DDoS, insider threats, or disclosure rules.",
    "Could you rephrase that? I'm best with incident-response topics like containment, "
    "MTTD/MTTR, or chain of custody.",
]

GREETINGS = ["hi", "hello", "hey", "sup", "yo"]


class ChatbotAssistantFrame(tb.Frame):
    """Chat panel with keyword-matched IR guidance."""

    def __init__(self, master, current_scenario_getter: Optional[Callable] = None):
        super().__init__(master, padding=15)
        self.current_scenario_getter = current_scenario_getter

        tb.Label(self, text=f"🤖 {BOT_NAME} — Trainee Assistant",
                  font=("Segoe UI", 16, "bold"), bootstyle="info").pack(anchor=W, pady=(0, 10))

        self.history = tk.Text(self, height=16, wrap="word", state=DISABLED,
                                 bg="#1e1e1e", fg="#e6e6e6", relief="flat",
                                 font=("Segoe UI", 10), padx=10, pady=10)
        self.history.tag_configure("bot", foreground="#5bc0de")
        self.history.tag_configure("user", foreground="#f0ad4e")
        self.history.pack(fill=BOTH, expand=True, pady=(0, 10))

        controls = tb.Frame(self)
        controls.pack(fill=X)

        self.entry = tb.Entry(controls, font=("Segoe UI", 11))
        self.entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 8))
        self.entry.bind("<Return>", lambda e: self._send())

        tb.Button(controls, text="Send", bootstyle="info", command=self._send).pack(side=LEFT)
        tb.Button(controls, text="💡 Hint for this scenario", bootstyle="warning-outline",
                   command=self._scenario_hint).pack(side=LEFT, padx=(8, 0))

        self._bot_say(
            f"Hi, I'm {BOT_NAME}. Ask me about containment, forensics, phishing, "
            "ransomware, disclosure rules, or what MTTD/MTTR mean — or tap the hint "
            "button for guidance on your current scenario."
        )

    def _send(self):
        text = self.entry.get().strip()
        if not text:
            return
        self.entry.delete(0, END)
        self._user_say(text)
        reply = self._generate_reply(text)
        self.after(300, lambda: self._bot_say(reply))

    def _scenario_hint(self):
        scenario = self.current_scenario_getter() if self.current_scenario_getter else None
        if not scenario:
            self._bot_say("I don't see an active scenario right now — start one and ask me again!")
            return
        title = scenario.get("situation") or scenario.get("title") or "this scenario"
        hint = self._hint_for_scenario(scenario)
        self._bot_say(f"On \"{title[:80]}\": {hint}")

    def _hint_for_scenario(self, scenario: dict) -> str:
        text = (scenario.get("situation", "") + " " + str(scenario.get("options", ""))).lower()
        for keyword, response in KNOWLEDGE_BASE.items():
            if keyword in text:
                return response
        return ("Think about the standard IR order of operations: identify, contain, "
                "eradicate, recover, then document lessons learned. Which step does "
                "this decision map to?")

    def _generate_reply(self, user_text: str) -> str:
        lowered = user_text.lower()
        if any(g in lowered for g in GREETINGS):
            return "Hey there! Ask me anything about incident response, or tap the hint button."
        for keyword, response in KNOWLEDGE_BASE.items():
            if keyword in lowered:
                return response
        return random.choice(FALLBACK_REPLIES)

    def _bot_say(self, text):
        self._append(f"{BOT_NAME}: ", "bot", text)

    def _user_say(self, text):
        self._append("You: ", "user", text)

    def _append(self, prefix, tag, text):
        self.history.config(state=NORMAL)
        self.history.insert(END, prefix, tag)
        self.history.insert(END, text + "\n\n")
        self.history.see(END)
        self.history.config(state=DISABLED)


# ============================================================
# SECTION 4 — AI-DRIVEN SCENARIO GENERATION
# ============================================================
# Fully offline template-based generator by default (no API key or
# internet required, works out of the box). If an ANTHROPIC_API_KEY
# environment variable is present AND the `anthropic` package is
# installed, generation is instead delegated to the Claude API for
# genuinely novel, freeform scenarios — with automatic fallback to
# the offline generator if that call fails for any reason.

THREAT_TYPES = [
    "SQL Injection", "Cross-Site Scripting (XSS)", "DDoS Attack", "DNS Spoofing",
    "Worm Outbreak", "Ransomware", "Phishing Email", "Spear Phishing", "Vishing Call",
    "Social Engineering", "Insider Threat", "Data Exfiltration", "Server Breach",
    "Zero-Day Exploit", "Credential Stuffing", "Man-in-the-Middle Attack",
]

TARGETS = [
    "the customer-facing web portal", "an internal file server", "the finance department's mailbox",
    "a third-party vendor integration", "the HR database", "a cloud storage bucket",
    "the employee VPN gateway", "a point-of-sale terminal", "the company's public API",
]

BEST_PRACTICE_ACTIONS = [
    "Isolate the affected system, preserve logs/evidence, and follow the documented IR playbook before making further changes.",
    "Verify the request/activity independently through a known-good channel before taking any action.",
    "Escalate to the appropriate team (legal, HR, or senior IR lead) rather than acting unilaterally.",
    "Patch the root cause and validate the fix in a safe environment before declaring the incident resolved.",
]

RISKY_ACTIONS = [
    "Take the fastest visible action (e.g., shut everything down or delete data) without preserving evidence first.",
    "Assume it's a false alarm and take no action.",
    "Handle it alone without looping in the required stakeholders.",
    "Comply immediately with the request exactly as it was made, no verification.",
]

# ---------------- ROLE-BASED SCENARIOS ----------------
# EXTRA FEATURE: same underlying incident, but the trainee answers from
# the perspective of a specific IR role — each role has its own realistic
# best-practice actions and its own realistic mistakes, rather than one
# generic "IT person" answer set.
ROLES = ["Any", "SOC Analyst", "Incident Commander", "Legal & PR Liaison"]

ROLE_BEST_PRACTICES = {
    "SOC Analyst": [
        "Isolate the affected host/segment immediately, capture logs and volatile evidence, and escalate to the Incident Commander with your findings.",
        "Correlate the alert against other log sources before escalating, to confirm it isn't a false positive.",
        "Follow the documented triage playbook step-by-step rather than skipping ahead to remediation.",
    ],
    "Incident Commander": [
        "Declare the incident formally, assign clear roles to the response team, and set a regular status-update cadence.",
        "Make the call on containment scope based on analyst input, balancing business impact against risk.",
        "Escalate to legal/PR and executive stakeholders as soon as scope or data-sensitivity thresholds are met.",
    ],
    "Legal & PR Liaison": [
        "Assess breach-notification obligations against the relevant regulations before any public statement is made.",
        "Coordinate a single, accurate public statement with IR/PR rather than letting individual teams speak independently.",
        "Advise IR to preserve evidence and communications in a way that protects legal privilege and future admissibility.",
    ],
}

ROLE_RISKY_ACTIONS = {
    "SOC Analyst": [
        "Shut down or wipe the affected system immediately without capturing any evidence first.",
        "Assume someone else is already handling it and take no action.",
        "Fix the surface symptom without documenting or escalating the underlying finding.",
    ],
    "Incident Commander": [
        "Let each team act independently with no single point of coordination.",
        "Delay declaring an incident until the scope is 100% certain, losing critical early response time.",
        "Make containment decisions without consulting the analysts who have the technical details.",
    ],
    "Legal & PR Liaison": [
        "Issue a public statement immediately, before confirming facts with the IR team.",
        "Stay silent and let the story break without any prepared response.",
        "Advise deleting or altering incident records to minimize apparent liability.",
    ],
}


class ScenarioGenerator:
    """Generates new practice scenarios in the same shape used by the
    Gamified Challenge (situation/options/correct/feedback)."""

    def __init__(self):
        self._anthropic_available = self._check_anthropic()

    def _check_anthropic(self) -> bool:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return False
        try:
            import anthropic  # noqa: F401
            return True
        except ImportError:
            return False

    def generate(self, domain: str = "Random", role: str = "Any") -> dict:
        """domain: 'Technical', 'Behavioral', 'Organizational', or 'Random'.
        role: 'Any', 'SOC Analyst', 'Incident Commander', or 'Legal & PR Liaison'
        — when a specific role is given, the scenario is written from that
        role's perspective, using that role's own realistic best-practice
        and risky actions instead of generic ones."""
        if self._anthropic_available:
            try:
                return self._generate_via_ai(domain, role)
            except Exception:
                pass  # silently fall back to the offline generator
        return self._generate_offline(domain, role)

    # ---------------- offline template generator ----------------
    def _generate_offline(self, domain: str, role: str = "Any") -> dict:
        threat = random.choice(THREAT_TYPES)
        target = random.choice(TARGETS)

        if role != "Any" and role in ROLE_BEST_PRACTICES:
            best = random.choice(ROLE_BEST_PRACTICES[role])
            risky_pool = ROLE_RISKY_ACTIONS[role]
        else:
            best = random.choice(BEST_PRACTICE_ACTIONS)
            risky_pool = RISKY_ACTIONS
        risky1 = random.choice(risky_pool)
        risky2 = random.choice([a for a in risky_pool if a != risky1])

        if role != "Any":
            situation = (
                f"[AI-Generated \u2014 {role} perspective] As the {role} responding to a suspected "
                f"{threat} affecting {target}, initial signals are still coming in and the scope "
                f"is unclear."
            )
        else:
            situation = (
                f"[AI-Generated] Monitoring tools flag a suspected {threat} affecting "
                f"{target}. Initial signals are still coming in and the scope is unclear."
            )

        # Randomize which displayed letter (A/B/C) holds the correct answer,
        # so it isn't predictably always "B".
        letters = ["A", "B", "C"]
        random.shuffle(letters)
        best_letter, risky1_letter, risky2_letter = letters

        options = {best_letter: best, risky1_letter: risky1, risky2_letter: risky2}
        correct = best_letter
        feedback = {
            best_letter: "Correct — this follows proper IR sequencing: contain/verify first, escalate appropriately.",
            risky1_letter: "This skips containment/verification and risks destroying evidence or overreacting.",
            risky2_letter: "This risks acting without the right authority or information — a similar pitfall to acting too early.",
        }
        return {
            "situation": situation,
            "options": options,
            "correct": correct,
            "feedback": feedback,
            "domain": domain,
            "role": role,
            "generated": True,
        }

    # ---------------- optional real AI generator ----------------
    def _generate_via_ai(self, domain: str, role: str = "Any") -> dict:
        import anthropic
        client = anthropic.Anthropic()
        role_clause = (
            f"Write it from the perspective of the '{role}' role specifically \u2014 the "
            f"situation and all three options must reflect decisions that role would "
            f"realistically face and make (not generic IT actions from an unrelated role). "
            if role != "Any" else ""
        )
        prompt = (
            f"Generate ONE realistic cybersecurity incident-response training scenario "
            f"in the '{domain}' domain. {role_clause}"
            f"Respond ONLY with strict JSON, no prose, no markdown "
            f"fences, matching exactly this shape: "
            f'{{"situation": "...", "options": {{"A": "...", "B": "...", "C": "..."}}, '
            f'"correct": "A|B|C", "feedback": {{"A": "...", "B": "...", "C": "..."}}}}. '
            f"Exactly one option must be the IR best-practice answer; the correct field must "
            f"name it."
        )
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in response.content if getattr(b, "type", "") == "text")
        data = json.loads(text.strip())
        data["domain"] = domain
        data["role"] = role
        data["generated"] = True
        return data


class ScenarioGeneratorFrame(tb.Frame):
    """GUI for on-demand AI-driven scenario generation + instant practice."""

    def __init__(self, master, engine: GamificationEngine = None,
                 metrics_tracker: "MetricsTracker" = None):
        super().__init__(master, padding=20)
        self.engine = engine
        self.metrics_tracker = metrics_tracker
        self.generator = ScenarioGenerator()
        self.current_scenario = None
        self.q_start_time = None

        header = tb.Frame(self)
        header.pack(fill=X, pady=(0, 10))
        tb.Label(header, text="🧠 AI-Driven Scenario Generation", font=("Segoe UI", 18, "bold"),
                  bootstyle="info").pack(side=LEFT)

        mode_note = "Live AI (Claude API)" if self.generator._anthropic_available else "Offline generator (no API key detected)"
        tb.Label(self, text=f"Mode: {mode_note}", bootstyle="secondary").pack(anchor=W, pady=(0, 10))

        controls = tb.Frame(self)
        controls.pack(fill=X, pady=(0, 15))
        tb.Label(controls, text="Domain:").pack(side=LEFT, padx=(0, 8))
        self.domain_var = tk.StringVar(value="Random")
        domain_menu = tb.Combobox(controls, textvariable=self.domain_var,
                                    values=["Random", "Technical", "Behavioral", "Organizational"],
                                    state="readonly", width=15)
        domain_menu.pack(side=LEFT, padx=(0, 10))

        tb.Label(controls, text="Role:").pack(side=LEFT, padx=(10, 8))
        self.role_var = tk.StringVar(value="Any")
        role_menu = tb.Combobox(controls, textvariable=self.role_var,
                                  values=ROLES, state="readonly", width=18)
        role_menu.pack(side=LEFT, padx=(0, 10))

        tb.Button(controls, text="✨ Generate New Scenario", bootstyle="success",
                   command=self._generate).pack(side=LEFT)

        tb.Label(self, text="Role-Based Scenarios: pick SOC Analyst, Incident Commander, or "
                             "Legal & PR Liaison to get the SAME kind of incident answered from "
                             "that role's own decisions and responsibilities \u2014 not one generic "
                             "\u201cIT person\u201d answer set.",
                  bootstyle="secondary", wraplength=700, justify=LEFT).pack(anchor=W, pady=(0, 10))

        self.body = tb.Frame(self)
        self.body.pack(fill=BOTH, expand=True)
        tb.Label(self.body, text="Click \"Generate New Scenario\" to create a fresh, "
                                   "on-the-spot practice incident.",
                  wraplength=700, justify=LEFT).pack(pady=20, anchor=W)

    def _generate(self):
        self.current_scenario = self.generator.generate(self.domain_var.get(), self.role_var.get())
        self._render()

    def _render(self):
        for w in self.body.winfo_children():
            w.destroy()
        q = self.current_scenario

        role_text = q.get("role", "Any")
        header_text = f"Domain: {q.get('domain', 'Random')}"
        if role_text and role_text != "Any":
            header_text += f"   |   Role: {role_text}"
        tb.Label(self.body, text=header_text, bootstyle="secondary").pack(anchor=W)
        tb.Label(self.body, text=q["situation"], font=("Segoe UI", 13),
                  wraplength=700, justify=LEFT).pack(pady=(5, 15), anchor=W)

        self.answer_buttons = {}
        for key in ("A", "B", "C"):
            btn = tb.Button(self.body, text=f"{key}. {q['options'][key]}",
                              bootstyle="outline-info", width=90,
                              command=lambda k=key: self._answer(k))
            btn.pack(fill=X, pady=4)
            self.answer_buttons[key] = btn

        self.feedback_label = tb.Label(self.body, text="", font=("Segoe UI", 10, "italic"),
                                         wraplength=700, justify=LEFT)
        self.feedback_label.pack(pady=(15, 0), anchor=W)

        tb.Button(self.body, text="🔁 Generate Another", bootstyle="secondary-outline",
                   command=self._generate).pack(pady=(15, 0), anchor=W)

        self.q_start_time = time.time()

    def _answer(self, chosen):
        q = self.current_scenario
        correct_key = q["correct"]
        is_correct = (chosen == correct_key)

        for btn in self.answer_buttons.values():
            btn.config(state=DISABLED)
        if chosen != correct_key:
            self.answer_buttons[chosen].config(bootstyle="danger")
        self.answer_buttons[correct_key].config(bootstyle="success")

        note = q["feedback"][chosen]
        if self.engine is not None:
            result = self.engine.award(is_correct)
            if result["xp_gained"]:
                note += f"\n+{result['xp_gained']} XP"
            for b in result["new_badges"]:
                note += f"\n{b['icon']} Badge unlocked: {b['label']}"

        if self.metrics_tracker is not None:
            now = time.time()
            self.metrics_tracker.log_incident(
                scenario_name="[AI-Generated] " + q["situation"][:50],
                detected_at=self.q_start_time, responded_at=now,
                resolved=is_correct, resolved_at=now,
            )

        self.feedback_label.config(text=note)


# ============================================================
# SECTION 5 — LIVE INCIDENT EMULATION + COLLABORATION MODE
# ============================================================
# A lightweight LAN-based "live SOC feed" — one trainee hosts a
# session (starts a local TCP server), others join using the host's
# IP address. The host's machine periodically emits a freshly
# AI-generated incident to everyone connected at the same moment,
# simulating a live, shared incident feed. A simple team chat runs
# alongside it. This is intentionally simple (JSON-line-over-socket,
# no auth) — meant for classroom/LAN training use, not production.

class IncidentBroadcaster:
    """Handles the raw networking for host or client role."""

    def __init__(self, on_message: Callable[[dict], None]):
        self.on_message = on_message
        self.sock = None
        self.is_host = False
        self.running = False
        self.clients = []  # host only: list of connected client sockets
        self._lock = threading.Lock()

    # ---------------- host ----------------
    def host(self, port: int):
        self.is_host = True
        self.running = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("0.0.0.0", port))
        self.sock.listen(8)
        threading.Thread(target=self._accept_loop, daemon=True).start()

    def _accept_loop(self):
        while self.running:
            try:
                conn, addr = self.sock.accept()
            except OSError:
                return
            with self._lock:
                self.clients.append(conn)
            threading.Thread(target=self._client_loop, args=(conn,), daemon=True).start()

    def _client_loop(self, conn):
        buffer = ""
        try:
            while self.running:
                data = conn.recv(4096)
                if not data:
                    break
                buffer += data.decode("utf-8", errors="ignore")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.strip():
                        msg = json.loads(line)
                        self.on_message(msg)
                        self.broadcast(msg, exclude=conn)
        except (ConnectionResetError, OSError):
            pass
        finally:
            with self._lock:
                if conn in self.clients:
                    self.clients.remove(conn)

    def broadcast(self, msg: dict, exclude=None):
        line = (json.dumps(msg) + "\n").encode("utf-8")
        with self._lock:
            for c in list(self.clients):
                if c is exclude:
                    continue
                try:
                    c.sendall(line)
                except OSError:
                    pass

    # ---------------- client ----------------
    def join(self, host_ip: str, port: int):
        self.is_host = False
        self.running = True
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((host_ip, port))
        threading.Thread(target=self._recv_loop, daemon=True).start()

    def _recv_loop(self):
        buffer = ""
        try:
            while self.running:
                data = self.sock.recv(4096)
                if not data:
                    break
                buffer += data.decode("utf-8", errors="ignore")
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.strip():
                        self.on_message(json.loads(line))
        except (ConnectionResetError, OSError):
            pass

    def send(self, msg: dict):
        """Send a message. Host broadcasts to all clients; client sends to host."""
        if self.is_host:
            self.on_message(msg)  # host sees its own message immediately
            self.broadcast(msg)
        elif self.sock:
            try:
                self.sock.sendall((json.dumps(msg) + "\n").encode("utf-8"))
            except OSError:
                pass

    def stop(self):
        self.running = False
        try:
            if self.sock:
                self.sock.close()
        except OSError:
            pass


class CloudRelay:
    """EXTRA FEATURE: Cloud Sync for Collaboration Mode.

    Lets teammates on DIFFERENT networks (not just the same LAN) share the
    same live-incident feed, chat, and scoreboard — joined by a shared
    Room Code instead of a host's local IP address.

    Implementation: uses a public MQTT broker (test.mosquitto.org) as a
    free relay, publishing/subscribing on a topic derived from the room
    code. Requires the 'paho-mqtt' package (pip install paho-mqtt) and an
    internet connection. Exposes the same send()/stop()/on_message
    interface as IncidentBroadcaster, so CollaborationFrame can use
    either one interchangeably.

    IMPORTANT — honesty about security: test.mosquitto.org is a public,
    unauthenticated test broker. Anyone who knows (or guesses) your exact
    room code can read and write to that room. Use a long, hard-to-guess
    room code, and treat this as suitable for training/demo collaboration
    only — not for anything sensitive or production-grade.
    """

    BROKER_HOST = "test.mosquitto.org"
    BROKER_PORT = 1883
    TOPIC_PREFIX = "irsim/room/"

    def __init__(self, on_message: Callable[[dict], None]):
        self.on_message = on_message
        self.client = None
        self.topic = None
        self.is_host = False  # here: "this peer generates incidents for the room"
        self.running = False

    def connect(self, room_code: str, as_generator: bool = False, timeout: float = 8.0):
        if not PAHO_AVAILABLE:
            raise RuntimeError("paho-mqtt is not installed — run: pip install paho-mqtt")
        self.topic = self.TOPIC_PREFIX + room_code.strip()
        self.is_host = as_generator

        try:
            self.client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION1)
        except AttributeError:
            self.client = mqtt.Client()  # older paho-mqtt (<2.0) has no CallbackAPIVersion

        self.client.on_message = self._on_mqtt_message
        self.client.connect(self.BROKER_HOST, self.BROKER_PORT, keepalive=30)
        self.client.subscribe(self.topic)
        self.client.loop_start()
        self.running = True

    def _on_mqtt_message(self, client, userdata, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
            self.on_message(data)
        except (json.JSONDecodeError, UnicodeDecodeError):
            pass

    def send(self, msg: dict):
        """Publish to the room topic. We're subscribed to our own topic too,
        so the broker echoes this back to us — no need to call on_message
        locally (that would double-count it)."""
        if self.client and self.running:
            try:
                self.client.publish(self.topic, json.dumps(msg))
            except Exception:
                pass

    def stop(self):
        self.running = False
        if self.client:
            try:
                self.client.loop_stop()
                self.client.disconnect()
            except Exception:
                pass


class CollaborationFrame(tb.Frame):
    """EXTRA FEATURE: Live Incident Emulation + Collaboration Mode.

    Host a session (or join one) so a whole team sees the same
    AI-generated incident appear live and can discuss it in a shared
    chat while everyone submits their own response independently.
    """

    def __init__(self, master, engine: GamificationEngine = None):
        super().__init__(master, padding=20)
        self.engine = engine
        self.generator = ScenarioGenerator()
        self.broadcaster = None
        self.msg_queue = queue.Queue()
        self.player_name = "Trainee"
        self.live_incident = None
        self.feed_job = None

        tb.Label(self, text="📡 Live Incident Emulation & Collaboration Mode",
                  font=("Segoe UI", 18, "bold"), bootstyle="info").pack(anchor=W, pady=(0, 10))

        self._build_connect_bar()
        self._build_layout()

        self.after(300, self._poll_queue)

    def _build_connect_bar(self):
        bar = tb.Labelframe(self, text="Session", padding=10)
        bar.pack(fill=X, pady=(0, 10))

        tb.Label(bar, text="Your name:").grid(row=0, column=0, sticky=W, padx=4, pady=4)
        self.name_entry = tb.Entry(bar, width=16)
        self.name_entry.insert(0, "Trainee")
        self.name_entry.grid(row=0, column=1, sticky=W, padx=4, pady=4)

        tb.Label(bar, text="Port:").grid(row=0, column=2, sticky=W, padx=4, pady=4)
        self.port_entry = tb.Entry(bar, width=8)
        self.port_entry.insert(0, "50505")
        self.port_entry.grid(row=0, column=3, sticky=W, padx=4, pady=4)

        tb.Label(bar, text="Role focus:").grid(row=0, column=5, sticky=W, padx=(14, 4), pady=4)
        self.session_role_var = tk.StringVar(value="Any")
        tb.Combobox(bar, textvariable=self.session_role_var, values=ROLES,
                     state="readonly", width=16).grid(row=0, column=6, sticky=W, padx=4, pady=4)

        tb.Button(bar, text="🖥 Host Session", bootstyle="success",
                   command=self._start_host).grid(row=0, column=4, padx=6)

        tb.Label(bar, text="Host IP:").grid(row=1, column=0, sticky=W, padx=4, pady=4)
        self.ip_entry = tb.Entry(bar, width=16)
        self.ip_entry.insert(0, "127.0.0.1")
        self.ip_entry.grid(row=1, column=1, sticky=W, padx=4, pady=4)

        tb.Button(bar, text="🔗 Join Session", bootstyle="info",
                   command=self._start_join).grid(row=1, column=4, padx=6)

        # --- Cloud Sync row: internet-wide collaboration via room code ---
        tb.Label(bar, text="☁ Room Code:").grid(row=2, column=0, sticky=W, padx=4, pady=(10, 4))
        self.cloud_room_entry = tb.Entry(bar, width=20)
        self.cloud_room_entry.grid(row=2, column=1, columnspan=2, sticky=W, padx=4, pady=(10, 4))

        self.cloud_generator_var = tk.BooleanVar(value=False)
        tb.Checkbutton(bar, text="I'll generate incidents for this room",
                         variable=self.cloud_generator_var, bootstyle="round-toggle"
                         ).grid(row=2, column=3, sticky=W, padx=4, pady=(10, 4))

        tb.Button(bar, text="☁ Connect to Cloud", bootstyle="warning",
                   command=self._start_cloud).grid(row=2, column=4, padx=6, pady=(10, 4))

        tb.Label(bar, text="Cloud mode works across different networks/locations (not just LAN) — "
                            "everyone using the same Room Code joins the same session. Needs an "
                            "internet connection and the 'paho-mqtt' package.",
                  bootstyle="secondary", wraplength=650, justify=LEFT
                  ).grid(row=3, column=0, columnspan=5, sticky=W, pady=(2, 0))

        self.status_label = tb.Label(bar, text="Not connected — host, join, or use a cloud room below.",
                                       bootstyle="secondary")
        self.status_label.grid(row=4, column=0, columnspan=5, sticky=W, pady=(8, 0))

    def _build_layout(self):
        row = tb.Frame(self)
        row.pack(fill=BOTH, expand=True)

        # Left: live incident panel
        left = tb.Labelframe(row, text="🚨 Live Incident Feed", padding=15)
        left.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10))
        self.incident_body = tb.Frame(left)
        self.incident_body.pack(fill=BOTH, expand=True)
        tb.Label(self.incident_body, text="No live incident yet. Host will push one shortly "
                                            "after starting the session.",
                  wraplength=380, justify=LEFT).pack(pady=10, anchor=W)

        # Right: team chat + scoreboard
        right = tb.Frame(row)
        right.pack(side=LEFT, fill=BOTH, expand=True)

        chat_box = tb.Labelframe(right, text="💬 Team Chat", padding=10)
        chat_box.pack(fill=BOTH, expand=True, pady=(0, 10))
        self.chat_history = tk.Text(chat_box, height=12, wrap="word", state=DISABLED,
                                      bg="#1e1e1e", fg="#e6e6e6", relief="flat", padx=8, pady=8)
        self.chat_history.pack(fill=BOTH, expand=True, pady=(0, 6))
        chat_controls = tb.Frame(chat_box)
        chat_controls.pack(fill=X)
        self.chat_entry = tb.Entry(chat_controls)
        self.chat_entry.pack(side=LEFT, fill=X, expand=True, padx=(0, 6))
        self.chat_entry.bind("<Return>", lambda e: self._send_chat())
        tb.Button(chat_controls, text="Send", bootstyle="info",
                   command=self._send_chat).pack(side=LEFT)

        score_box = tb.Labelframe(right, text="🏆 Team Scoreboard", padding=10)
        score_box.pack(fill=BOTH, expand=True)
        self.score_list = tk.Listbox(score_box, height=6, bg="#1e1e1e", fg="#e6e6e6",
                                       relief="flat")
        self.score_list.pack(fill=BOTH, expand=True)
        self.scores = {}

    # ---------------- session controls ----------------
    def _start_host(self):
        try:
            port = int(self.port_entry.get())
        except ValueError:
            self.status_label.config(text="⚠️ Invalid port number.")
            return
        self.player_name = self.name_entry.get() or "Host"
        self.broadcaster = IncidentBroadcaster(on_message=self.msg_queue.put)
        try:
            self.broadcaster.host(port)
        except OSError as e:
            self.status_label.config(text=f"⚠️ Could not start host: {e}")
            return
        local_ip = self._get_local_ip()
        self.status_label.config(
            text=f"✅ Hosting on {local_ip}:{port} — share this IP with your team."
        )
        self._push_system_chat(f"{self.player_name} started hosting the session.")
        self._schedule_next_incident(initial_delay=3000)

    def _start_join(self):
        try:
            port = int(self.port_entry.get())
        except ValueError:
            self.status_label.config(text="⚠️ Invalid port number.")
            return
        self.player_name = self.name_entry.get() or "Trainee"
        self.broadcaster = IncidentBroadcaster(on_message=self.msg_queue.put)
        try:
            self.broadcaster.join(self.ip_entry.get(), port)
        except OSError as e:
            self.status_label.config(text=f"⚠️ Could not join: {e}")
            return
        self.status_label.config(text=f"✅ Connected to {self.ip_entry.get()}:{port}")
        self.broadcaster.send({"type": "chat", "name": self.player_name,
                                 "text": "joined the session."})

    def _start_cloud(self):
        room = self.cloud_room_entry.get().strip()
        if not room:
            self.status_label.config(text="⚠️ Enter a Room Code first (any word/phrase — "
                                            "share it with your team so they can join the same room).")
            return
        if not PAHO_AVAILABLE:
            self.status_label.config(
                text="⚠️ Cloud mode needs the 'paho-mqtt' package. In a terminal, run: "
                     "pip install paho-mqtt — then try again."
            )
            return

        self.player_name = self.name_entry.get() or "Trainee"
        self.broadcaster = CloudRelay(on_message=self.msg_queue.put)
        try:
            self.broadcaster.connect(room, as_generator=self.cloud_generator_var.get())
        except Exception as e:
            self.status_label.config(text=f"⚠️ Cloud connect failed: {e}")
            return

        self.status_label.config(
            text=f"☁ Connected to cloud room \u2018{room}\u2019 — works across different networks/locations."
        )
        self._push_system_chat(f"{self.player_name} joined cloud room '{room}'.")
        self.broadcaster.send({"type": "chat", "name": self.player_name,
                                 "text": "joined the session (cloud)."})
        if self.broadcaster.is_host:
            self._schedule_next_incident(initial_delay=3000)

    def _get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except OSError:
            return "127.0.0.1"

    # ---------------- live incident emission (host only) ----------------
    def _schedule_next_incident(self, initial_delay=None):
        if self.broadcaster is None or not self.broadcaster.is_host:
            return
        delay = initial_delay if initial_delay is not None else random.randint(20000, 40000)
        self.feed_job = self.after(delay, self._emit_incident)

    def _emit_incident(self):
        role = self.session_role_var.get() if hasattr(self, "session_role_var") else "Any"
        scenario = self.generator.generate("Random", role)
        self.broadcaster.send({"type": "incident", "scenario": scenario,
                                 "issued_by": self.player_name,
                                 "timestamp": datetime.now().strftime("%H:%M:%S")})
        self._schedule_next_incident()

    # ---------------- chat ----------------
    def _send_chat(self):
        text = self.chat_entry.get().strip()
        if not text or self.broadcaster is None:
            return
        self.chat_entry.delete(0, END)
        self.broadcaster.send({"type": "chat", "name": self.player_name, "text": text})

    def _push_system_chat(self, text):
        self._render_chat("System", text)

    def _render_chat(self, name, text):
        self.chat_history.config(state=NORMAL)
        self.chat_history.insert(END, f"{name}: ", ("name",))
        self.chat_history.insert(END, text + "\n")
        self.chat_history.see(END)
        self.chat_history.config(state=DISABLED)

    # ---------------- incoming message handling ----------------
    def _poll_queue(self):
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                self._handle_message(msg)
        except queue.Empty:
            pass
        self.after(300, self._poll_queue)

    def _handle_message(self, msg: dict):
        mtype = msg.get("type")
        if mtype == "chat":
            self._render_chat(msg.get("name", "?"), msg.get("text", ""))
        elif mtype == "incident":
            self.live_incident = msg["scenario"]
            self._render_incident(msg)
            self._push_system_chat(f"🚨 New incident issued at {msg.get('timestamp', '')}")
        elif mtype == "score":
            self.scores[msg["name"]] = msg["xp"]
            self._render_scoreboard()

    def _render_incident(self, msg):
        for w in self.incident_body.winfo_children():
            w.destroy()
        q = msg["scenario"]
        tb.Label(self.incident_body, text=q["situation"], font=("Segoe UI", 11),
                  wraplength=380, justify=LEFT).pack(anchor=W, pady=(0, 10))

        self.live_answer_buttons = {}
        for key in ("A", "B", "C"):
            btn = tb.Button(self.incident_body, text=f"{key}. {q['options'][key]}",
                              bootstyle="outline-info", width=50,
                              command=lambda k=key: self._answer_live(k))
            btn.pack(fill=X, pady=3)
            self.live_answer_buttons[key] = btn

        self.live_feedback = tb.Label(self.incident_body, text="", font=("Segoe UI", 9, "italic"),
                                        wraplength=380, justify=LEFT)
        self.live_feedback.pack(pady=(8, 0), anchor=W)

    def _answer_live(self, chosen):
        if self.live_incident is None:
            return
        q = self.live_incident
        correct_key = q["correct"]
        is_correct = (chosen == correct_key)

        for btn in self.live_answer_buttons.values():
            btn.config(state=DISABLED)
        if chosen != correct_key:
            self.live_answer_buttons[chosen].config(bootstyle="danger")
        self.live_answer_buttons[correct_key].config(bootstyle="success")
        self.live_feedback.config(text=q["feedback"][chosen])

        xp_gained = 0
        if self.engine is not None:
            result = self.engine.award(is_correct)
            xp_gained = self.engine.progress["xp"]

        if self.broadcaster is not None:
            self.broadcaster.send({"type": "score", "name": self.player_name,
                                     "xp": xp_gained})

    def _render_scoreboard(self):
        self.score_list.delete(0, END)
        for name, xp in sorted(self.scores.items(), key=lambda kv: kv[1], reverse=True):
            self.score_list.insert(END, f"{name} — {xp} XP")


# ============================================================
# SECTION 6 — PROJECT INFO PAGE (logo + team details)
# ============================================================

PROJECT_INFO_FILE = "project_info.json"

# Default team details shown on the Project Info page. These pre-fill the
# form on first launch (and for any field left blank in project_info.json).
# Anything edited and saved through the GUI overrides these.
DEFAULT_TEAM_MEMBERS = [
    {"name": "Varalakshmi P",         "emp_id": "ST#IS#10154", "email": "27varlakshmi@gmail.com"},
    {"name": "Omkar Sudhir Wachhe",   "emp_id": "ST#IS#10155", "email": "omkarwachhe80@gmail.com"},
    {"name": "Ashwini R",             "emp_id": "ST#IS#10156", "email": "ashwinireddy01ash@gmail.com"},
    {"name": "Abhishek Meti",         "emp_id": "ST#IS#10157", "email": "abhishekmeti9632@gmail.com"},
]


class ProjectInfoFrame(tb.Frame):
    """Home page: tool logo/icon (drawn, no external image needed) +
    editable Project Info showing all TEAM MEMBERS at once
    (Name, Emp ID, Email per member) as per the project notes."""

    TEAM_SIZE = 4

    def __init__(self, master):
        super().__init__(master, padding=30)
        self._build_logo()
        tb.Label(self, text="Incident Response Simulator", font=("Segoe UI", 22, "bold"),
                  bootstyle="info").pack(pady=(10, 0))
        tb.Label(self, text="Cybersecurity training & incident-response practice tool",
                  bootstyle="secondary").pack(pady=(0, 25))

        form = tb.Labelframe(self, text="Project Info — Team Details", padding=15)
        form.pack(fill=X)

        # header row
        tb.Label(form, text="#", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, padx=6, pady=(0, 8))
        tb.Label(form, text="Name", font=("Segoe UI", 9, "bold")).grid(row=0, column=1, padx=6, pady=(0, 8))
        tb.Label(form, text="Emp ID", font=("Segoe UI", 9, "bold")).grid(row=0, column=2, padx=6, pady=(0, 8))
        tb.Label(form, text="Email", font=("Segoe UI", 9, "bold")).grid(row=0, column=3, padx=6, pady=(0, 8))

        # One row of Name / Emp ID / Email per team member, all visible together.
        self.member_vars = []
        for m in range(self.TEAM_SIZE):
            row = m + 1
            tb.Label(form, text=f"{m + 1}.").grid(row=row, column=0, padx=6, pady=4)
            name_var = tk.StringVar()
            emp_var = tk.StringVar()
            email_var = tk.StringVar()
            tb.Entry(form, textvariable=name_var, width=20).grid(row=row, column=1, padx=6, pady=4)
            tb.Entry(form, textvariable=emp_var, width=14).grid(row=row, column=2, padx=6, pady=4)
            tb.Entry(form, textvariable=email_var, width=28).grid(row=row, column=3, padx=6, pady=4)
            self.member_vars.append({"name": name_var, "emp_id": emp_var, "email": email_var})

        tb.Button(form, text="💾 Save All", bootstyle="success",
                   command=self._save).grid(row=self.TEAM_SIZE + 1, column=0, columnspan=4, pady=(12, 0))
        self.status = tb.Label(form, text="", bootstyle="secondary")
        self.status.grid(row=self.TEAM_SIZE + 2, column=0, columnspan=4)

        self._load()

    def _build_logo(self):
        ico_path, png_path = generate_logo_icon()
        if png_path and os.path.exists(png_path):
            # Keep a reference on the instance so it isn't garbage-collected.
            self._logo_img = tk.PhotoImage(file=png_path).subsample(2, 2)  # 256 -> 128
            tb.Label(self, image=self._logo_img).pack()
        else:
            # Fallback if PIL isn't installed — simple drawn placeholder.
            canvas = tk.Canvas(self, width=90, height=100, highlightthickness=0, bg="#1e1e1e", bd=0)
            canvas.pack()
            canvas.create_polygon(45, 5, 85, 20, 85, 55, 45, 95, 5, 55, 5, 20,
                                    fill="#3fa7d6", outline="#1c5d78", width=2)
            canvas.create_text(45, 50, text="🛡", font=("Segoe UI", 28))

    def _load(self):
        # 1) Pre-fill every row with the default team details.
        for i, defaults in enumerate(DEFAULT_TEAM_MEMBERS[:self.TEAM_SIZE]):
            for key in ("name", "emp_id", "email"):
                self.member_vars[i][key].set(defaults.get(key, ""))

        # 2) Overlay anything previously saved (only non-blank values, so an
        #    old empty project_info.json doesn't wipe out the defaults).
        if os.path.exists(PROJECT_INFO_FILE):
            try:
                with open(PROJECT_INFO_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                members = data.get("members", [])
                for i, member_data in enumerate(members[:self.TEAM_SIZE]):
                    for key in ("name", "emp_id", "email"):
                        value = (member_data.get(key) or "").strip()
                        if value:
                            self.member_vars[i][key].set(value)
            except (json.JSONDecodeError, OSError):
                pass

    def _save(self):
        members = [
            {k: v.get() for k, v in member.items()}
            for member in self.member_vars
        ]
        data = {"members": members}
        with open(PROJECT_INFO_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        self.status.config(text="Saved ✅ — all 4 members stored")


# ============================================================
# SECTION 7 — MAIN APPLICATION SHELL (Proper Tool GUI, all options)
# ============================================================

class MainApplication(tb.Window):
    """The full application: a sidebar-navigation shell that ties
    every feature together as one proper GUI, instead of separate
    demo windows."""

    def __init__(self):
        super().__init__(themename="darkly")
        self.title("Incident Response Simulator")
        self.geometry("1150x780")
        self.minsize(950, 650)
        self._set_app_icon()

        self.engine = GamificationEngine(trainee_name="Trainee", emp_id="EMP0001")
        self.tracker = MetricsTracker(storage_path="metrics_history.json")

        self._build_sidebar()
        self._build_content_area()
        self._build_pages()
        self.show_page("home")

    def _set_app_icon(self):
        """Places the generated logo as the real title-bar/taskbar icon."""
        ico_path, png_path = generate_logo_icon()
        try:
            if os.name == "nt" and ico_path and os.path.exists(ico_path):
                self.iconbitmap(ico_path)
            elif png_path and os.path.exists(png_path):
                self._app_icon_img = tk.PhotoImage(file=png_path)
                self.iconphoto(True, self._app_icon_img)
        except Exception:
            pass  # icon is cosmetic — never let it block the app from launching

    def _build_sidebar(self):
        sidebar = tb.Frame(self, bootstyle="dark", width=220)
        sidebar.pack(side=LEFT, fill=Y)
        sidebar.pack_propagate(False)

        header = tb.Frame(sidebar, bootstyle="dark")
        header.pack(pady=(20, 25), padx=15, anchor=W, fill=X)

        _, png_path = generate_logo_icon()
        if png_path and os.path.exists(png_path):
            self._sidebar_logo_img = tk.PhotoImage(file=png_path).subsample(8, 8)  # 256 -> 32
            tb.Label(header, image=self._sidebar_logo_img, bootstyle="inverse-dark").pack(side=LEFT, padx=(0, 8))

        tb.Label(header, text="IR Simulator", font=("Segoe UI", 14, "bold"),
                  bootstyle="inverse-dark").pack(side=LEFT)

        self.nav_buttons = {}
        nav_items = [
            ("home", "🏠  Project Info"),
            ("challenge", "🎮  Gamified Challenge"),
            ("generator", "🧠  AI Scenario Generator"),
            ("collab", "📡  Live Incident + Collab"),
            ("dashboard", "📊  Metrics Dashboard"),
            ("chatbot", "🤖  IR Buddy"),
        ]
        for key, label in nav_items:
            btn = tb.Button(sidebar, text=label, bootstyle="secondary-outline",
                              command=lambda k=key: self.show_page(k))
            btn.pack(fill=X, padx=12, pady=4)
            self.nav_buttons[key] = btn

    def _build_content_area(self):
        self.content = tb.Frame(self)
        self.content.pack(side=LEFT, fill=BOTH, expand=True)

    def _build_pages(self):
        self.pages = {}

        self.pages["home"] = ProjectInfoFrame(self.content)
        self.pages["challenge"] = GamifiedChallengeFrame(
            self.content, self.engine, metrics_tracker=self.tracker)
        self.pages["generator"] = ScenarioGeneratorFrame(
            self.content, engine=self.engine, metrics_tracker=self.tracker)
        self.pages["collab"] = CollaborationFrame(self.content, engine=self.engine)
        self.pages["dashboard"] = MetricsDashboardFrame(self.content, self.tracker)
        self.pages["chatbot"] = ChatbotAssistantFrame(
            self.content,
            current_scenario_getter=lambda: (
                self.pages["challenge"].scenario["questions"][self.pages["challenge"].q_index]
                if self.pages["challenge"].q_index < len(self.pages["challenge"].scenario["questions"])
                else None
            ),
        )

        for page in self.pages.values():
            page.place(x=0, y=0, relwidth=1, relheight=1)

    def show_page(self, key: str):
        self.pages[key].tkraise()
        if key == "dashboard":
            self.pages["dashboard"]._refresh()
        for k, btn in self.nav_buttons.items():
            btn.config(bootstyle="info" if k == key else "secondary-outline")


def launch_app():
    """Launches the full Incident Response Simulator (all six features)."""
    app = MainApplication()
    app.mainloop()


# Backward-compatible alias used by earlier versions of this file.
launch_demo_app = launch_app


if __name__ == "__main__":
    ensure_admin()
    launch_app()
