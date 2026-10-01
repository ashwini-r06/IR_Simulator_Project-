# 🛡️ Incident Response Simulator

A desktop cybersecurity training tool for practising incident-response decisions. It combines a gamified challenge, AI-driven scenario generation, live team collaboration, a chatbot assistant and an MTTD/MTTR metrics dashboard in a single sidebar-navigation GUI.

Built with Python, Tkinter and [ttkbootstrap](https://ttkbootstrap.readthedocs.io/).

\---

## Team

|#|Name|Emp ID|Email|
|-|-|-|-|
|1|Varalakshmi P|ST#IS#10154|27varlakshmi@gmail.com|
|2|Omkar Sudhir Wachhe|ST#IS#10155|omkarwachhe80@gmail.com|
|3|Ashwini R|ST#IS#10156|ashwinireddy01ash@gmail.com|
|4|Abhishek Meti|ST#IS#10157|abhishekmeti9632@gmail.com|

These details are pre-filled on the **Project Info** page and can be edited and saved in the app.

\---

## Features

|Page|What it does|
|-|-|
|🏠 **Project Info**|Tool logo and editable team details (Name, Emp ID, Email for each member).|
|🎮 **Gamified Challenge**|14 self-paced incident-response questions with XP, levels, streaks, badges and a leaderboard. No timer. You can go back and review answers, and option order is shuffled each play.|
|🧠 **AI Scenario Generator**|Generates fresh scenarios by domain (Technical / Behavioral / Organizational) and by role (SOC Analyst, Incident Commander, Legal \& PR Liaison). Works offline out of the box.|
|📡 **Live Incident + Collab**|Host or join a shared live incident feed with team chat and a scoreboard, over LAN or over the internet using a Room Code (Cloud Sync).|
|📊 **Metrics Dashboard**|MTTD and MTTR gauges, correct-resolution rate, a trend chart and a table of recent incidents.|
|🤖 **IR Buddy**|Keyword-based chatbot covering containment, forensics, phishing, ransomware, DDoS, SQL injection, insider threats, disclosure rules and more, plus a context hint for the question on screen.|

The tool also follows the project requirement to **run with Administrator access**. On Windows, launching the script triggers a UAC prompt automatically.

\---

## Requirements

* Python 3.9 or newer
* Windows (recommended, needed for the Administrator auto-elevation). It also runs on macOS/Linux; use `sudo` if you want elevated rights.
* On Linux, install Tk first: `sudo apt install python3-tk`

Python packages are listed in [`requirements.txt`](requirements.txt):

|Package|Needed for|Required?|
|-|-|-|
|`ttkbootstrap`|GUI theme and widgets|Yes|
|`matplotlib`|Dashboard trend chart|Yes|
|`Pillow`|Generating the logo and app icon|Recommended|
|`paho-mqtt`|Cloud Sync (collaboration across networks)|Recommended|
|`anthropic`|Live AI scenario generation|Optional|

\---

## Installation

```bash
# 1. (Optional) create a virtual environment
python -m venv venv
venv\\Scripts\\activate          # Windows
# source venv/bin/activate     # macOS / Linux

# 2. Install dependencies
pip install -r requirements.txt
```

\---

## Running the tool

```bash
python incident_response.py.py
```

Accept the UAC prompt on Windows. The app relaunches itself with Administrator rights. If you decline, it continues without them.

On first run the tool creates an `assets/` folder containing `icon.png` and `icon.ico` (the shield logo).

\---

## Using the features

### Gamified Challenge

Click **Begin Challenge**, pick A/B/C for each situation, and read the feedback. Use **◀ Previous / Next ▶** to move between questions. Correct answers give +25 XP; wrong answers reset your streak. Finish with zero mistakes for the 💎 Flawless Round badge.

### AI Scenario Generator

Choose a **Domain** and **Role**, then click **✨ Generate New Scenario**.

* **Offline mode (default):** template-based, needs no key or internet.
* **Live AI mode:** install `anthropic` and set your API key before launching. If the API call fails, the tool silently falls back to offline mode.

```bash
# Windows (PowerShell)
$env:ANTHROPIC\_API\_KEY = "your-key-here"
# Windows (cmd)
set ANTHROPIC\_API\_KEY=your-key-here
# macOS / Linux
export ANTHROPIC\_API\_KEY="your-key-here"
```

### Live Incident + Collaboration

**LAN mode**

1. One person clicks **🖥 Host Session** (default port `50505`) and shares the IP address shown.
2. Everyone else enters the host's IP and clicks **🔗 Join Session**.
3. The host pushes a new incident to all players every 20 to 40 seconds.

**Cloud mode (different networks)**

1. Everyone enters the same **Room Code**.
2. One person ticks *"I'll generate incidents for this room"*.
3. Click **☁ Connect to Cloud** (needs internet and `paho-mqtt`).

> ⚠️ Cloud mode uses the public, unauthenticated broker `test.mosquitto.org`. Anyone who guesses your Room Code can read and post in the room. Use a long, hard-to-guess code, and use it for training and demos only. LAN mode also has no authentication, so only use it on trusted networks.

### Metrics Dashboard

Every answered question is logged as an incident. MTTD is the average time to answer, and MTTR is the average time to a correct resolution. Click **🔄 Refresh Dashboard** to update.

\---

## Building a Windows executable

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --uac-admin --collect-data ttkbootstrap --name IR_Simulator incident_response.py.py
```

The result is `dist\\IR\_Simulator.exe`. To use the shield as the exe icon, run the script once so `assets\\icon.ico` exists, then add `--icon assets\\icon.ico` to the command.

Flag notes:

* `--uac-admin` makes the exe request Administrator access on launch.
* `--collect-data ttkbootstrap` bundles the theme files so the exe starts correctly.

\---

## Data files

The tool saves these next to where it is launched from:

|File|Contents|
|-|-|
|`project\_info.json`|Saved team details from the Project Info page|
|`leaderboard.json`|XP, level, streak and badges per trainee|
|`metrics\_history.json`|Logged incidents used by the dashboard|
|`assets/icon.png`, `assets/icon.ico`|Generated logo and app icon|

Delete a file to reset that data.

\---

## Project structure

```
incident_response.py.py  # the whole application
requirements.txt        # Python dependencies
README.md               # this file
assets/                 # generated on first run (logo/icon)
```

Inside `incident\_response.py`:

|Section|Contents|
|-|-|
|0|Administrator elevation (`ensure\_admin`)|
|1|Gamification (`GamificationEngine`, `GamifiedChallengeFrame`)|
|2|Metrics (`MetricsTracker`, `MetricsDashboardFrame`)|
|3|Chatbot (`ChatbotAssistantFrame`)|
|4|Scenario generation (`ScenarioGenerator`, `ScenarioGeneratorFrame`)|
|5|Collaboration (`IncidentBroadcaster`, `CloudRelay`, `CollaborationFrame`)|
|6|Project Info page (`ProjectInfoFrame`, `DEFAULT\_TEAM\_MEMBERS`)|
|7|Main window and sidebar (`MainApplication`)|

\---

## Troubleshooting

|Problem|Fix|
|-|-|
|`ModuleNotFoundError`|Run `pip install -r requirements.txt`|
|Cloud Sync says `paho-mqtt` is missing|`pip install paho-mqtt`|
|No logo or icon shown|`pip install Pillow`|
|Cannot join a LAN session|Check the host's IP, port `50505`, and that the firewall allows it|
|exe crashes with theme errors|Rebuild with `--collect-data ttkbootstrap`|

\---

## 

