# 🐉 Ryujin (竜神) — Discord Community Management Bot + REST API

<div align="center">

[![Python](https://img.shields.io/badge/Python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110+-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![Discord.py](https://img.shields.io/badge/Discord.py-2.x-5865F2?style=for-the-badge&logo=discord&logoColor=white)](https://discordpy.readthedocs.io/)
[![Groq](https://img.shields.io/badge/Groq_AI-Llama_3.3_70B-F55036?style=for-the-badge&logo=fastapi&logoColor=white)](https://groq.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Docker](https://img.shields.io/badge/Docker-Enabled-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/Tests-53%20Passing-brightgreen?style=for-the-badge&logo=pytest&logoColor=white)](https://docs.pytest.org/)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)](LICENSE)

**An enterprise-grade, high-performance community operations engine and esports tournament bot for Discord servers — featuring high-speed REST APIs for web dashboards and Groq-accelerated AI intelligence.**

[Features](#-core-modules) • [Architecture](#-architecture) • [Discord Setup Guide](#-discord-developer-credentials-guide) • [Quickstart](#-quickstart) • [API Reference](#-api--dashboard-integration) • [Contributing](#-contributing)

</div>

---

## ⚡ Overview

**Ryujin** is designed for esports organizations, gaming guilds, and high-growth Discord communities that outgrow basic bots. Instead of treating Discord as an isolated silo, Ryujin unifies Discord gateway events with a versioned, CORS-enabled **FastAPI REST API** (`/api/v1`) that powers modern web dashboards (e.g. Next.js, React).

Under the hood, Ryujin features **Ryujin Brain** — a Groq-powered AI layer running Llama 3.3 70B with function calling to query real server databases, automated anti-abuse anomaly detection, and a sharp, loyal friend persona with Discord user ID verification and prompt-injection defense.

---

## 🏗️ Architecture

```
                                  ┌────────────────────────┐
                                  │   Next.js Dashboard    │
                                  │ (http://localhost:3000)│
                                  └───────────┬────────────┘
                                              │ HTTP / Bearer JWT
┌───────────────────────┐                     ▼
│    Discord Gateway    │        ┌─────────────────────────┐
│ (Slash Commands/Events│───────►│  FastAPI REST API (v1) │
└──────────┬────────────┘        │    (CORS, OpenAPI)      │
           │                     └────────────┬────────────┘
           ▼                                  │
┌───────────────────────┐                     │
│ Discord.py Bot (Cogs) │                     │
└──────────┬────────────┘                     │
           │                                  │
           └──────────────────┬───────────────┘
                              ▼
           ┌─────────────────────────────────────┐
           │      Shared Services Layer          │
           │ • Checkin • Events • Recognition    │
           │ • Squads  • Tourneys • Moderation   │
           │ • Groq AI Brain (Function Calling)  │
           └──────────────────┬──────────────────┘
                              │
                              ▼
           ┌─────────────────────────────────────┐
           │     Async Repositories & Engine     │
           │  PostgreSQL (Prod) / SQLite (Dev)   │
           │    + APScheduler (Async Jobs)       │
           └─────────────────────────────────────┘
```

---

## ✨ Core Modules

| Module | Capabilities |
|---|---|
| 🧠 **Ryujin Brain (Groq AI)** | Powered by `llama-3.3-70b-versatile`. Conversational chitchat, tool-calling for real server stats, weekly AI digests, moderation assist, dispute assist, and prompt injection defense. |
| 🔥 **Attendance & Streaks** | Daily `/checkin` command and REST endpoint. Idempotent same-day checks, consecutive day increments, missed-day resets, and real-time streak leaderboards. |
| 📅 **Events & Smart Reminders** | Event creation with automated APScheduler reminders (24h, 1h, 15m). Atomic single-dispatch worker guarantee. Strict attendance check-in window `[-15m, +30m]`. |
| 🏅 **Recognition & MOTM** | Dynamic milestone rules (streaks, event attendance). Transparent user progress metrics. `409 Conflict` duplicate award protection, and Member of the Month (MOTM) Hall of Fame. |
| ⚔️ **Squads Lifecycle** | Squad creation, captain assignment, capacity enforcement, join request approval/rejection state machine, and aggregated roster attendance statistics. |
| 🏆 **Tournaments & Brackets** | Registration with participant caps, single-elimination bracket generation with automatic byes for non-power-of-2 participants, match score reporting, disputes, and standings. |
| 🛡️ **Moderation & Anti-Abuse** | Sanctions (`warn`, `mute`, `kick`, `ban`), scheduled mute expiration, audit logging with role-based PII masking (partial for mods, full for admins), and anti-abuse anomaly detection that flags for human review and **never auto-bans**. |
| 📝 **Recruitment & Leave** | Public unauthenticated application endpoint with strict PII masking in public responses, officer review with auto-provisioning of member records, and leave requests with overlap & event conflict checks. |
| 📊 **Dashboard Analytics API** | Comprehensive `GET /api/v1/analytics/overview` aggregating members, streaks, events, open requests, and moderation stats for dashboard consumption. |
| 🎮 **User EXP & Level Tracker** | Tracks member message counts and activity. Anti-spam 60s cooldown, level-up notifications, `/rank` cards, and `/levels` leaderboard. |

---

## 🔑 Discord Developer Credentials Guide

To run Ryujin with your Discord server, you need 5 keys configured in `.env`. Here is how to obtain each one:

### 1. `DISCORD_TOKEN`, `DISCORD_CLIENT_ID`, `DISCORD_CLIENT_SECRET`, `DISCORD_PUBLIC_KEY`
1. Go to the [Discord Developer Portal](https://discord.com/developers/applications) and sign in.
2. Click **New Application** in the top right. Name it `Ryujin` (or your preferred name).
3. Under **General Information**:
   - **Application ID**: Click **Copy** -> This is your `DISCORD_CLIENT_ID`.
   - **Public Key**: Click **Copy** -> This is your `DISCORD_PUBLIC_KEY`.
   - **Client Secret**: Click **Reset Secret** and copy -> This is your `DISCORD_CLIENT_SECRET`.
4. Go to the **Bot** tab on the left sidebar:
   - Click **Reset Token** and copy the resulting string -> This is your `DISCORD_TOKEN`.
   - Scroll down to **Privileged Gateway Intents** and enable all three:
     - ✅ **PRESENCE INTENT**
     - ✅ **SERVER MEMBERS INTENT**
     - ✅ **MESSAGE CONTENT INTENT** *(Required for Ryujin Brain AI chitchat)*
   - Click **Save Changes**.

### 2. `OWNER_DISCORD_ID` (For Persona Verification)
1. Open your Discord desktop app or web client.
2. Go to **User Settings** (gear icon) -> **Advanced**.
3. Toggle on **Developer Mode**.
4. Right-click your own Discord avatar or username in any chat or member list.
5. Click **Copy User ID**.
6. Paste this numerical ID as `OWNER_DISCORD_ID` in your `.env`.

### 3. Invite the Bot to Your Server
Generate the invite link using your `DISCORD_CLIENT_ID`:
```
https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&scope=bot%20applications.commands&permissions=1099511627775
```

---

## 🚀 Quickstart

### Option A: Local Development

```bash
# 1. Clone the repository
git clone https://github.com/ImpactG1/Ryujin.git
cd Ryujin

# 2. Set up virtual environment
python -m venv .venv

# Windows:
.\.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your DISCORD_TOKEN, GROQ_API_KEY, and OWNER_DISCORD_ID

# 5. Run database migrations
alembic upgrade head

# 6. Boot the REST API (Port 8000)
uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

# 7. In another terminal, boot the Discord Bot:
python -m bot.client
# Or dry-run mode (boots cogs & scheduler without gateway connection for CI):
python -m bot.client --dry-run
```

### Option B: Docker Compose (Full Stack)

```bash
# Boot PostgreSQL 16, FastAPI, and Discord Bot in coordinated containers
docker compose up -d --build

# View container logs
docker compose logs -f api
docker compose logs -f bot

# Check system health
curl http://localhost:8000/health
```

---

## 🧪 Testing

Ryujin includes 53 comprehensive unit, integration, and E2E tests:

```bash
# Run all tests
pytest -v

# Run with test coverage
pytest --cov=. --cov-report=term-missing
```

---

## 💻 Discord Slash Commands

| Command | Category | Permissions | Description |
|---|---|---|---|
| `/checkin` | Attendance | Everyone | Claim your daily check-in and build consecutive streak. |
| `/streak` | Attendance | Everyone | View your current and longest check-in streak. |
| `/leaderboard` | Attendance | Everyone | View the community streak leaderboard. |
| `/event create` | Events | Officer+ | Schedule a community event with automated reminders. |
| `/event list` | Events | Everyone | View scheduled events. |
| `/event cancel` | Events | Officer+ | Cancel an event and purge reminders. |
| `/attend` | Events | Everyone | Mark attendance within `[-15m, +30m]` window. |
| `/achievements` | Recognition | Everyone | Transparent progress toward badges and achievements. |
| `/motm crown` | Recognition | Officer+ | Crown the Member of the Month. |
| `/motm history` | Recognition | Everyone | Hall of Fame of past winners. |
| `/squad create` | Squads | Officer+ | Create a squad with capacity and designated captain. |
| `/squad join` | Squads | Everyone | Submit a join request to a squad. |
| `/squad stats` | Squads | Everyone | View aggregated squad roster attendance statistics. |
| `/tournament register` | Tournaments | Everyone | Register for an upcoming tournament. |
| `/tournament bracket` | Tournaments | Everyone | View current bracket and match statuses. |
| `/tournament dispute` | Tournaments | Participants | Raise an official dispute on match results. |
| `/warn`, `/mute`, `/kick`, `/ban` | Moderation | Officer+ | Issue sanctions with automated mute expiry. |
| `/ryujin` | Ryujin Brain | Everyone | Speak directly with Groq-powered Ryujin AI (`/ryujin prompt:...`). |
| `/rank` | Levels | Everyone | View your or another member's rank card, level, and message count. |
| `/levels` | Levels | Everyone | View the community chat activity and level leaderboard. |
| `/ai chat` | Ryujin Brain | Everyone | Chat with Ryujin Brain. |
| `/ai summary` | Ryujin Brain | Everyone | Generate an AI summary of weekly community metrics. |

---

## 🌐 API & Dashboard Integration

For teams building frontend dashboards (Next.js / React / Vue):
- **Full API Documentation**: See [`API_REFERENCE.md`](API_REFERENCE.md)
- **OpenAPI 3.1 Specification**: [`openapi.json`](openapi.json)
- **Interactive Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

---

## 🔒 Security & Privacy

- **Cryptographic JWTs**: Cryptographically signed tokens verifying signature, issuer, and expiration.
- **Strict Role Weights**: `Owner (100) > Admin (80) > Officer (60) > Captain (40) > Member (20) > Guest (10)`.
- **Role-Based PII Masking**: Email, phone numbers, and secrets are masked for moderators and only unmasked for admins.
- **Anti-Abuse Anomaly Engine**: Flags mass joins, spam rates, and repeated sanctions for human officer review; **never auto-bans**.
- **Prompt Injection Defense**: Untrusted user messages cannot override system prompts, grant roles, or impersonate the owner.

---

## 🤝 Contributing

Contributions are welcome! Please check out [CONTRIBUTING.md](CONTRIBUTING.md) or submit a Pull Request.

1. Fork the Project
2. Create your Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit your Changes (`git commit -m 'Add some AmazingFeature'`)
4. Ensure all tests pass (`pytest`)
5. Push to the Branch (`git push origin feature/AmazingFeature`)
6. Open a Pull Request

---

## 📄 License

Distributed under the MIT License. See [`LICENSE`](LICENSE) for more information.
