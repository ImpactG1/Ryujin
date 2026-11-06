# Ryujin REST API Reference (v1)

Base URL: `http://localhost:8000/api/v1`  
Interactive Swagger Docs: `http://localhost:8000/docs`  
OpenAPI JSON Specification: [openapi.json](file:///d:/Applications/Ryujin/openapi.json)  
CORS Enabled Origins: `http://localhost:3000`

---

## Authentication & Headers
- All private endpoints require a Bearer token:
  ```http
  Authorization: Bearer <jwt_token>
  ```
- Public endpoints (e.g. `/guilds/{guild_id}/recruitment/apply`, `/health`) do NOT require authentication.
- Permissions: Standard Discord bitwise permission checks and role weights (`owner`: 100 > `admin`: 80 > `officer`: 60 > `captain`: 40 > `member`: 20 > `guest`: 10).

---

## 1. System Health
- **GET `/health`**
  - Response: `{"status": "ok", "app": "Ryujin", "version": "1.0.0"}`

---

## 2. Attendance & Daily Check-Ins
- **POST `/guilds/{guild_id}/checkin`**
  - Header: `Authorization: Bearer <token>`
  - Idempotent: Can be called multiple times per day without double-counting.
  - Response:
    ```json
    {
      "success": true,
      "already_checked_in": false,
      "streak_count": 5,
      "longest_streak": 12,
      "checkin_date": "2026-11-02",
      "message": "Check-in successful! Your streak is now 5 days."
    }
    ```
- **GET `/guilds/{guild_id}/streaks/leaderboard?limit=10`**
  - Returns top streaks ranked by current streak count.
- **GET `/guilds/{guild_id}/members/{user_id}/streak`**
  - Returns member's current and longest streak statistics.

---

## 3. Events & Reminders
- **POST `/guilds/{guild_id}/events`** (Officer+)
  - Body:
    ```json
    {
      "title": "Weekly Scrim",
      "description": "5v5 internal matches",
      "start_time": "2026-11-05T18:00:00Z",
      "end_time": "2026-11-05T20:00:00Z",
      "target_squad_id": null
    }
    ```
  - Automatically schedules 24h, 1h, and 15m reminders with atomic dispatch.
- **GET `/guilds/{guild_id}/events?status=scheduled&limit=50`**
  - Lists scheduled community events.
- **PATCH `/guilds/{guild_id}/events/{event_id}`** (Officer+)
  - Updates title, description, or start/end time. Reschedules reminders if start time changes.
- **DELETE `/guilds/{guild_id}/events/{event_id}`** (Officer+)
  - Cancels event and purges undispatched reminders.
- **POST `/guilds/{guild_id}/events/{event_id}/attend`**
  - Enforces check-in window: [start_time - 15m, start_time + 30m].
  - Returns 400 Bad Request if called outside the active window.

---

## 4. Recognition & Member of the Month (MOTM)
- **POST `/guilds/{guild_id}/achievements`** (Officer+)
  - Body: `code`, `name`, `description`, `criteria_type` ('streak' or 'events_attended'), `threshold`, `badge_icon`.
- **GET `/guilds/{guild_id}/members/{user_id}/achievements/progress`**
  - Returns transparent progress (`current_value`, `threshold`, `percentage`, `is_unlocked`, `awarded_at`).
- **POST `/guilds/{guild_id}/achievements/{achievement_id}/award`** (Officer+)
  - Body: `{"target_user_id": 123456}`
  - Protected: Returns `409 Conflict` if the achievement has already been awarded.
- **POST `/guilds/{guild_id}/motm`** (Officer+)
  - Body: `{"year_month": "2026-11", "target_user_id": 123456, "reason": "Outstanding leadership"}`
- **GET `/guilds/{guild_id}/motm/history`**
  - Returns MOTM Hall of Fame ordered by month descending.

---

## 5. Squads Lifecycle
- **POST `/guilds/{guild_id}/squads`** (Officer+)
  - Body: `{"name": "Shadow Blades", "captain_id": 123456, "capacity": 10}`
- **GET `/guilds/{guild_id}/squads`**
  - List all squads.
- **POST `/guilds/{guild_id}/squads/{squad_id}/join-requests`**
  - Member submits join request. Returns `400` if squad is full, `409` if pending/already member.
- **POST `/guilds/{guild_id}/squads/{squad_id}/join-requests/{request_id}/review`** (Captain or Officer)
  - Body: `{"decision": "approved" | "rejected", "notes": "..."}`
- **GET `/guilds/{guild_id}/squads/{squad_id}/stats`**
  - Aggregated squad attendance percentage and per-member breakdown.

---

## 6. Recruitment & Leave
- **POST `/guilds/{guild_id}/recruitment/apply`** (**PUBLIC - NO AUTH REQUIRED**)
  - Body:
    ```json
    {
      "discord_tag": "Ace#0001",
      "email": "ace@domain.com",
      "full_name": "Ace Ventura",
      "experience": "Semi-pro tournament player",
      "answers": {"role": "Captain"},
      "discord_user_id": 123456789
    }
    ```
  - Response: Sensitive PII (email, name) is strictly masked.
- **GET `/guilds/{guild_id}/recruitment/applications`** (Officer+)
  - Officer inspection of pending applications with full details.
- **POST `/guilds/{guild_id}/recruitment/applications/{application_id}/review`** (Officer+)
  - Body: `{"decision": "approved" | "rejected"}`
  - Auto-provisions community member record upon approval.
- **POST `/guilds/{guild_id}/leave-requests`**
  - Body: `{"start_date": "2026-11-15", "end_date": "2026-11-20", "reason": "Vacation"}`
  - Returns `409 Conflict` if overlapping with an existing leave. Returns warnings for conflicting events.

---

## 7. Tournaments & Standings
- **POST `/guilds/{guild_id}/tournaments`** (Officer+)
  - Creates tournament with participant cap (`max_participants`).
- **POST `/guilds/{guild_id}/tournaments/{id}/register`**
  - Member registers. Returns 400 if cap reached.
- **POST `/guilds/{guild_id}/tournaments/{id}/generate-bracket`** (Officer+)
  - Generates single-elimination bracket handling byes for non-powers of 2.
- **GET `/guilds/{guild_id}/tournaments/{id}/bracket`**
  - Returns all matches by round and match number.
- **POST `/guilds/{guild_id}/tournaments/{id}/matches/{match_id}/score`**
  - Reporter (participant or officer) submits match scores. Advances winner to next round or crowns tournament champion.
- **POST `/guilds/{guild_id}/tournaments/{id}/matches/{match_id}/dispute`**
  - Participant raises dispute on match.
- **POST `/guilds/{guild_id}/tournaments/{id}/disputes/{dispute_id}/resolve`** (Officer+)
  - Officer resolves dispute and advances chosen winner.
- **GET `/guilds/{guild_id}/tournaments/{id}/standings`**
  - Returns ranked standings (Champion, Runner-Up, Semi-Finalists).

---

## 8. Moderation & Anti-Abuse
- **POST `/guilds/{guild_id}/moderation/sanctions`** (Officer+)
  - Body: `{"target_user_id": 123456, "sanction_type": "warn" | "mute" | "kick" | "ban", "reason": "...", "duration_minutes": 60}`
  - Mutes automatically schedule an expiry job via APScheduler.
- **GET `/guilds/{guild_id}/audit-logs`** (Officer / Admin)
  - Role-based PII masking: Officers see masked emails/names/tokens; Admins see full data.
- **GET `/guilds/{guild_id}/moderation/anomalies`** (Officer+)
  - Evaluates real-time spam rates, mass joins, and repeated sanctions. Flags for human review and NEVER auto-bans.

---

## 9. Levels & Hunter Rank Tiers (D, C, B, A, S, SS, SSS)
- **GET `/guilds/{guild_id}/members/{user_id}/rank`**
  - Returns member rank card, letter rank tier (`D` to `SSS`), Ryujin's shy 1-line quote, current level, and XP progression.
  - Response:
    ```json
    {
      "guild_id": 123456789,
      "discord_user_id": "987654321",
      "rank": 1,
      "rank_tier": "A",
      "previous_rank_tier": "B",
      "rank_updated_at": "2026-11-06T12:00:00Z",
      "shy_quote": "Rank A. Keep this up and you might actually impress me.",
      "level": 32,
      "total_xp": 1450,
      "current_level_xp": 45,
      "xp_needed_for_next": 295,
      "progress_percent": 15.3,
      "messages_count": 84,
      "last_message_at": "2026-11-06T11:00:00Z"
    }
    ```
- **GET `/guilds/{guild_id}/levels/leaderboard?limit=10`**
  - Returns community level and chat activity leaderboard ranked by total XP with `rank_tier`.
- **POST `/guilds/{guild_id}/members/{user_id}/xp`** (Officer+)
  - Body: `{"xp_delta": 250}`
  - Manually grant or adjust a member's experience points.
- **POST `/guilds/{guild_id}/members/{user_id}/rank/promote`** (Officer+)
  - Body: `{"target_tier": "S", "reason": "Tournament MVP"}`
  - Manually promotes a member to next or specified tier. Logs audit event and rank history.
- **POST `/guilds/{guild_id}/members/{user_id}/rank/demote`** (Officer+)
  - Body: `{"target_tier": "B", "reason": "Disciplinary demotion"}`
  - Manually demotes a member to lower tier. Logs audit event and rank history.
- **GET `/guilds/{guild_id}/members/{user_id}/rank/history`**
  - Fetches the member's complete timeline of promotions and demotions.
- **POST `/guilds/{guild_id}/members/{user_id}/rank/sync`**
  - Body: `{"discord_tier": "S"}`
  - Syncs the rank tier detected from Discord roles, automatically recording promotions/demotions.

---

## 10. Dashboard Analytics Overview
- **GET `/api/v1/analytics/overview`** (or `/guilds/{guild_id}/analytics/overview`)
  - Response:
    ```json
    {
      "guild_id": 123456789,
      "members": { "total": 125, "active": 98 },
      "attendance": { "active_streaks": 45, "average_streak": 6.8 },
      "events": { "upcoming_count": 3, "next_events": [...] },
      "open_requests": { "recruitment_applications": 2, "leave_requests": 1, "total_open": 3 },
      "moderation": { "active_sanctions_count": 4, "breakdown": { "warn": 3, "mute": 1 } },
      "tournaments": { "active_tournaments": 1 }
    }
    ```
- **GET `/guilds/{guild_id}/members?page=1&page_size=20&search=...&active_only=true`**
  - Paginated table endpoint for Next.js member directory.

---

## 10. Groq AI Layer ("Ryujin Brain")
- **POST `/guilds/{guild_id}/ai/chat`**
  - Body: `{"message": "When is the next scrimmage?", "channel_id": 1000000000}`
  - Employs function calling against real DB events/streaks (never hallucinates facts).
- **GET `/guilds/{guild_id}/ai/summary`**
  - AI generated weekly digest based on real server metrics.
- **POST `/guilds/{guild_id}/ai/mod-assist`** (Officer+)
  - Suggests sanction severity and reasoning for officer review.
- **POST `/guilds/{guild_id}/ai/dispute-assist`** (Officer+)
  - Impartially summarizes dispute claims for officers.

