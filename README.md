#  Event Planet — The Tiny Book

Hello little friend! 👋

This is **Event Planet**. It is a robot brain 🤖 that helps grown-ups plan **parties, races, hackathons and big meetings** — and it never gets tired.

You (yes, YOU!) are going to make it come alive. It is as easy as making a sandwich. 🥪 Let's go!

---

## 🍩 1. What can this robot do?

Imagine you throw a birthday party:

| The robot can... | Like when you... |
|---|---|
| 🎪 Keep a list of parties (we call them **Events**) | Keep your toy list |
| 🪜 Cut a party into little steps (**Stages**) — like "cake time", "game time" | Cut your sandwich in halves |
| 📝 Let friends write their name down (**Register**) so they can come | Your friends raising their hands: "Me! Me!" |
| 🎟️ Say how many friends may come (**Capacity**) — the seats are limited! | You have only 10 chairs |
| ⭐ Let friends say if the party was fun (**Feedback**: 1 to 5 stars) | Showing thumbs up 👍 |
| 🏆 Tell everyone who won (**Results**) | The winner gets a gold star ⭐ |

And the best part: **the robot is very fair and follows the rules.** Nobody can sneak in. 🚫🦹

---

## 🌱 2. The life of a party (very important!)

Every party grows up like a seed becomes a flower:

```
 🌱 DRAFT  ──▶  🌷 PUBLISHED  ──  🔒 CLOSED  ──▶  🏁 FINISHED
 (secret!)     (friends can       (no more         (party over,
                sign up now)       signing up)      stars & winners now)
```

The robot **only allows these exact steps, in this exact order.** You cannot jump from 🌱 to 🏁. That's the rule! (The rules live in the "service layer" — that's the robot's tummy. No one is allowed to cheat around it.)

---

## 🚀 3. Turn the robot ON (3 magic steps)

You need two magic tools installed first: **Docker** (a magic box that runs robots) and **Docker Compose** (its helper).

### Step 1 — Copy the secret paper 📄

```bash
cp .env.example .env
```

This copies the "secret settings paper" so you can look at it.

### Step 2 — Say the magic words ✨

```bash
docker compose up --build
```

Now watch! The robot will:
1. 🔌 Wait until the big memory box (**PostgreSQL** database) is awake
2. 🏗️ Build all its shelves (**migrations**)
3. 🧹 Tidy its room (**collectstatic**)
4. 👋 Start talking on **http://localhost:8000**

That's it. **One command. The robot is alive!** 🎉

### Step 3 — Say hello 👋

Open your browser and go to `http://localhost:8000/api/v1/public/events/`
If you see `[]` (an empty list — no parties yet), everything works! 🥳

> 💡 **To turn the robot OFF:** press `Ctrl` + `C` in the terminal.
> **To erase everything and start fresh:** `docker compose down -v`

---

##  4. The secret paper (.env)

The robot reads this paper to know your secrets. You can change the words after the `=` sign:

```ini
SECRET_KEY=a-very-long-secret-nobody-knows     # the robot's diary lock 🔒
DEBUG=false                                    # false = grown-up mode (fast), true = kid mode (shows errors)
ALLOWED_HOSTS=*                                # who may talk to the robot (* = anybody)

POSTGRES_DB=event_planet                       # the name of the memory box
POSTGRES_USER=event_planet                     # the name of the memory keeper
POSTGRES_PASSWORD=event_planet                 # the memory keeper's password

DB_HOST=db                                     # where the memory box lives (inside Docker: "db")
DB_PORT=5432                                   # the memory box's door number

JWT_SECRET=another-long-secret                 # the lock for magic entry badges 🔑
JWT_ALGORITHM=HS256                            # the badge-making recipe (leave it)

# DJANGO_SUPERUSER_USERNAME=admin              # optional: make the BOSS user automatically
# DJANGO_SUPERUSER_PASSWORD=super-secret-123
# DJANGO_SUPERUSER_EMAIL=admin@example.com
```

> ⚠️ **Grown-up rule:** in a real deployment, ALWAYS change `SECRET_KEY` and `JWT_SECRET` to long random strings, and set `DEBUG=false`. Never tell anyone your secrets! 🤫

---

## 👑 5. Make the BOSS user (superuser)

The **BOSS** (superuser) can go everywhere, even the secret admin room.

**Easy way — while the robot is running, open a second terminal and type:**

```bash
docker compose exec web python manage.py createsuperuser
```

Answer the questions (username, email, password). Done! 👑

**Automatic way:** put these in your `.env` BEFORE `docker compose up`, and the robot makes the BOSS by itself:

```ini
DJANGO_SUPERUSER_USERNAME=admin
DJANGO_SUPERUSER_PASSWORD=super-secret-123
DJANGO_SUPERUSER_EMAIL=admin@example.com
```

Then visit `http://localhost:8000/admin/` — the secret admin room! 🏰

---

## 🎭 6. Two kinds of friends (roles)

There are only **two kinds** of users. When you sign up, you pick one:

| Role | What they do |
|---|---|
| 🧑‍🎤 **Organizer** | Makes parties. Only THEY can edit their own parties. Like the birthday kid! 🎂 |
| 🙋 **Participant** | Signs up for parties, gives stars afterwards. Like the guests! |

**The golden rule:** an organizer can NEVER touch another organizer's party. The robot hides other people's parties from them completely (it answers 404: "I don't see any such party!" 🙈).

Fun fact: a guest can still be a **speaker or judge** for one little step of a party (we call those stage roles: `speaker`, `judge`, `coach`, `instructor`, `moderator`, `other`). Wearing a judge hat doesn't change who you are! 🎩

---

## 📮 7. What can I say to the robot? (the API)

The robot listens on doors called **endpoints**. You send it a message (with your magic badge = JWT token), it answers with JSON. There are three neighborhoods:

### 🌍 Public neighborhood (no badge needed)

| What | Door (endpoint) |
|---|---|
| See all published parties | `GET /api/v1/public/events/` |
| Peek inside one party | `GET /api/v1/public/events/{id}/` |
| See the winners | `GET /api/v1/public/events/{id}/results/` |

### 🙋 Participant neighborhood (needs a participant badge)

| What | Door (endpoint) |
|---|---|
| Get your badge | `POST /api/v1/auth/token/` (then `/token/refresh/`, `/token/verify/`) |
| Make an account | `POST /api/v1/auth/register/` |
| Sign up for a party | `POST /api/v1/participant/events/{event_id}/register/` |
| See MY sign-ups | `GET /api/v1/participant/registrations/` |
| Change my mind (cancel) | `POST /api/v1/participant/registrations/{id}/cancel/` |
| Give stars (only AFTER the party is finished!) | `POST /api/v1/participant/events/{event_id}/feedback/` |

### 🧑‍🎤 Organizer neighborhood (needs an organizer badge)

| What | Door (endpoint) |
|---|---|
| Make / edit / delete MY parties | `/api/v1/organizer/events/…` |
| Grow the party one step (draft→published→…) | `POST /api/v1/organizer/events/{id}/status/` |
| See who signed up | `GET /api/v1/organizer/events/{id}/participants/` |
| Read the stars people gave | `GET /api/v1/organizer/events/{id}/feedback/` |
| Make little steps (stages) | `/api/v1/organizer/events/{event_id}/stages/…` |
| Give stage hats (speaker, judge…) | `/api/v1/organizer/events/{event_id}/stages/{stage_id}/roles/…` |
| Make question types (attributes) | `/api/v1/organizer/attributes/…` |
| Answer the questions for MY party | `/api/v1/organizer/events/{event_id}/attribute-values/…` |
| Write down who won (results) | `/api/v1/organizer/events/{event_id}/results/…` |
| Show the winners to the world | `POST …/results/{id}/publish/` or `POST …/results/publish-all/` |

### 🔑 How do I get a badge? (JWT in 10 seconds)

```bash
# 1. Ask for a badge (you get a long magic string called "access")
curl -X POST http://localhost:8000/api/v1/auth/token/ \
  -H 'Content-Type: application/json' \
  -d '{"username":"boss","password":"YOUR_PASSWORD"}'

# 2. Show the badge on every visit:
curl http://localhost:8000/api/v1/organizer/events/ \
  -H "Authorization: Bearer PASTE_THE_ACCESS_STRING_HERE"
```

Badges get old after a while (1 hour). Ask for a fresh one with `POST /api/v1/auth/token/refresh/`.

---

##  8. The rules of the playground (the robot ALWAYS checks)

1. 🙈 **Secret parties stay secret.** Draft parties are invisible to the public. The robot doesn't peek either!
2. 🪑 **No more than the chairs!** If capacity is 10, person #11 is politely told "no seat left" (400). Even if 100 people press the button at the SAME moment — the robot makes them stand in one line (a database row-lock) so nobody can sneak in. 🚦
3. 🙅 **One name, one party.** You cannot sign up twice. The database itself says "no!" — not just the robot's manners.
4. 👑 **Only the owner edits.** Not the other organizers. Not the guests. Only the birthday kid.
5. 🪜 **The party grows in order.** draft → published → closed → finished. No skipping, no going back.
6. ⭐ **Stars only after the party.** You must have SIGNED UP, and the party must be FINISHED. No star-spam!
7. 🏆 **Winners only after the party,** announced only by the owner, and then the whole world may see them.
8. 🏷️ **Parties have little labels** (attributes): "how many rounds?", "is it online?" — each label has a strict type (word, number, yes/no, date, or a pick-one-from-list). No messy "anything goes" boxes (we NEVER use JSONField for them — everything is tidy and typed, like sorted Lego bricks 🧱).

> 🧠 **A tiny technical secret (for when you're bigger):** signing up and capacity live on the **whole event**, never on a single stage. Stages are just the "plan of the day" (agenda). This was decided on purpose and written down here so everyone remembers.

---

##  9. The "check everything" button (tests)

The robot comes with **103 tiny robots inside that check the big robot** — rules, locks, hats, stars, winners, everything!

```bash
# If the robot is running in Docker:
docker compose exec web python manage.py test

# Or at home without Docker (Python only):
python manage.py test -v 1
```

If you see **OK** — everything is good in the world. 🌈

---

## 🤖 10. No UI? No problem!

This robot has **no buttons and no pictures** on purpose. It is **API-first**: it only speaks JSON.

Any website or app (a phone app, a webpage, anything) can *wear* the pretty clothes by talking to these endpoints. The robot stays the brain 🧠, the website stays the face 😊. If you build a UI one day, just make sure it only talks to the robot through these doors — all the rules stay inside the robot, where they are safe.

---

## 🛠️ 11. When something goes wrong (tiny fixes)

| Problem | Magic fix |
|---|---|
| `docker compose up` says port 8000 is busy | Another robot sits there. Turn it off, or change `"8000:8000"` to `"8001:8000"` in `docker-compose.yml` |
| Robot can't find the database | Wait 10 seconds — the database is still waking up. The robot already waits patiently for it ⏳ |
| `401 Unauthorized` | Your badge is missing or old. Get a new one from `/auth/token/` |
| `403 Forbidden` | Wrong neighborhood! Participants can't knock on organizer doors |
| `404 Not Found` | The thing doesn't exist — OR it belongs to someone else (the robot hides strangers' toys) |
| I broke everything | `docker compose down -v && docker compose up --build` — fresh start! 🔄 |

---

## 🎓 12. For grown-ups (the boring-but-important part)

**Stack:** Python 3.12 · Django 5.2 · Django REST Framework · PostgreSQL 16 · JWT (SimpleJWT) · Gunicorn · Docker (multi-stage build, non-root user) · WhiteNoise for static files.

**Project layout:**

```
config/      settings (all from env vars), urls, wsgi
accounts/    User (one global role) + Profile + JWT endpoints
events/      Event, Stage, StageRole, Attribute (EAV catalog) + services
registrations/  Registration, Feedback + services
results/     Result + publish flow
common/      permission classes: IsOrganizer, IsParticipant, IsEventOwner,
             IsRegisteredParticipant, IsEventFinished
tests/       103 automated tests
```

**Design decisions (documented, tested, enforced):**
- **Registration & capacity are EVENT-level.** Stages carry no capacity; they are organizational only.
- **Status changes only via the service layer** (`EventService.change_status`); `status` is never writable through serializers.
- **EAV, not JSONField.** `Attribute` (global, shared catalog with unique `key` + `data_type`) → `AttributeOption` (for `choice`) → `EventAttributeValue` (typed columns: `value_text/_integer/_decimal/_boolean/_date/_option`, unique per `(event, attribute)`). `AttributeService` validates every value and type-safety is guaranteed before the DB ever sees it.
- **Race-safe capacity:** `RegistrationService.register` wraps everything in one transaction and takes `SELECT … FOR UPDATE` on the event row; concurrent last-seat requests serialize and exactly one wins (proven by the threaded test on PostgreSQL).
- **Cancel = soft delete.** The row flips to `cancelled` (freeing a seat); signing up again re-activates the same row, so `unique(event, participant)` always holds.
- **Feedback is an upsert** (one row per event+participant); **results are flexible** (participant XOR team, optional rank/score/notes) with an explicit `publish_at` gate (scheduled publishing supported).
- **Defense in depth:** permission classes block at the HTTP boundary AND services re-check the rules; owner-filtered querysets mean foreign objects 404.

**Environment variables:** see section 4 — every one of them is optional with a sane dev default, and `docker-compose.yml` wires them automatically.

---

Made with 💛 — now go throw a party on Event Planet! 🪐🎉
