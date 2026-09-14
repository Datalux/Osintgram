# Osintgram Web UI — user guide

A local web interface for Osintgram. You give it an Instagram username, pick
what you want to know (or just ask in plain language), and it collects the
answer from Instagram and lays it out on the page — profile details, follower
lists, post statistics, maps, heatmaps, media previews.

Everything runs on your own machine. The page is served from `127.0.0.1`, the
optional AI model runs locally through Ollama, and the only thing that leaves
your computer is the request to the Instagram data backend.

> **This tool has no login.** It is built to run on your own machine and is
> bound to `127.0.0.1` on purpose. Don't move it onto a network interface
> without putting an authentication layer in front of it first.

**Contents**

1. [Requirements](#1-requirements)
2. [Setup](#2-setup)
3. [Your first search](#3-your-first-search)
4. [The two modes: AI and Base](#4-the-two-modes-ai-and-base)
5. [What you can ask for](#5-what-you-can-ask-for)
6. [Keeping the cost down](#6-keeping-the-cost-down)
7. [Reading the results](#7-reading-the-results)
8. [Saving, comparing, exporting](#8-saving-comparing-exporting)
9. [Configuration reference](#9-configuration-reference)
10. [Troubleshooting](#10-troubleshooting)
11. [What it stores on disk](#11-what-it-stores-on-disk)

---

## 1. Requirements

| | Needed for | Notes |
|---|---|---|
| Python 3.10+ with `requirements.txt` | everything | the floor FastAPI and uvicorn require |
| A **data backend** | everything | HikerAPI key (paid, recommended) or an instagrapi login — see [Setup](#22-choose-a-data-backend) |
| **Ollama** + a tool-calling model | AI mode only | Base mode works without it |
| A browser | everything | any modern one |

Base mode needs no Ollama at all. If you don't want to run a local LLM, skip
step 2.3 and use Base mode — every command is available there.

---

## 2. Setup

### 2.1 Install

```bash
pip install -r requirements.txt
```

### 2.2 Choose a data backend

Instagram data comes through one of two interchangeable backends.

**HikerAPI** (recommended) is a paid third-party service. It's the default,
it needs no Instagram account of yours, and it supports every command.

You don't have to edit any file: start the server (step 2.4) and the page will
open on a **🔑 HikerAPI key** panel. Paste your key there and press
**"Verify and use"** — the key is checked against HikerAPI's free balance
endpoint, so you find out immediately whether it works:

```
✓ Key valid — 474 requests left, saved to file
```

Leave **"Remember in config/credentials.ini"** ticked and the key is written to
the same file the tool reads on the next start.
Untick it and the key lives only until you stop the server.

You can still configure it the old way if you prefer — either is fine:

```bash
export HIKERAPI_TOKEN=your_key_here
```

```ini
# config/credentials.ini
[Credentials]
hikerapi_token = your_key_here
```

If more than one is set, the order is **`HIKERAPI_TOKEN` → key entered in the
UI → `config/credentials.ini`**. The panel always names the one in use, so a
key that is being overridden says so rather than silently doing nothing.

Once a key is set, the 🔑 chip in the title bar (next to your credit) reopens
the panel to replace it. The key is never displayed again — only a masked
preview like `hik_…9f2c`.

**instagrapi** (free, higher risk) logs into Instagram directly with a real
username and password. It costs nothing, but Instagram can flag or challenge
the account you use, so **use a secondary account, never your main one**.

1. Put the username and password in `config/credentials.ini` under
   `[Credentials]`, or set `INSTAGRAM_USERNAME` / `INSTAGRAM_PASSWORD`.
2. Run `python scripts/instagrapi_login.py` **once, from a terminal** — this
   is the only place a 2FA or challenge code can be typed in. It saves a
   session to `config/instagrapi_session.json`.
3. Leave `HIKERAPI_TOKEN` unset so instagrapi is picked automatically, or
   force it with `export INSTAGRAM_BACKEND=instagrapi`.

The web app never attempts an interactive login itself: if the session expires
or Instagram challenges it, re-run the script.

Both backends run every command except **"Suggested profiles"** and
**"Account info"**, which have no instagrapi equivalent and say so
instead of returning an empty result. "Profile info" works on both, though
instagrapi exposes a slightly smaller field set.

### 2.3 Install Ollama (AI mode only)

1. Install [Ollama](https://ollama.com/download) and make sure it's running
   (`ollama serve`; on macOS and Windows it starts on its own after install).
2. Pull a model that supports tool calling:

```bash
ollama pull llama3.1:8b     # ~4.7 GB, the default
ollama pull qwen2.5:7b      # a solid alternative
```

Pick a different one with `export OLLAMA_MODEL=qwen2.5:7b`. The model must
support tool calling — one that doesn't will answer from thin air instead of
running commands.

**Give it enough context.** Ollama loads every model with a 4096-token window
unless told otherwise, however large a context the model itself advertises.
That is too small here: the 28 tool schemas plus the system prompt come to
roughly 2,000 tokens before a single result arrives, so the second or third
tool call overflows the window — and Ollama discards the *oldest* tokens, which
are precisely the system prompt and the tool definitions. The model then looks
incompetent (forgets its instructions, stops calling tools, starts making
answers up) when it simply can't see them any more.

The app therefore asks for `OLLAMA_NUM_CTX=16384`. That costs roughly 2 GB of
KV cache on an 8B model. If you're short on memory, lower it — but not below
about 8192, or you're back to truncation. If you have room, raising it lets the
model hold more results at once.

**Bigger models are noticeably better at choosing tools.** `llama3.1:8b` is the
default because it is small and widely available, not because it is the best
here: with 28 tools to choose from, an 8B model picks the wrong one more often
and is likelier to mangle an argument. If you can run one, a 14B–24B
tool-calling model is a clear step up. Ollama's library marks models that
support tools; anything without that capability will not work in AI mode at
all.

### 2.4 Start it

```bash
uvicorn src.web.app:app --host 127.0.0.1 --port 8000 --reload
```

or `make run`. Then open <http://127.0.0.1:8000>. Drop `--reload` for an
instance you intend to leave running.

### 2.5 Or run it in Docker

```bash
docker compose up --build      # or: make docker
```

Same address and same behaviour. **After pulling a newer version, run this
same command again** — `docker compose up` alone reuses whatever image was
last built even when the source has changed; only `--build` picks up new
code. `make docker` always includes it.

Three things are deliberate about the setup:

- The port is published as `127.0.0.1:8000:8000`, not `8000:8000` — the app
  has no authentication, so the container must not be reachable from your
  network. The `0.0.0.0` inside the Dockerfile is the *container's* own
  interface, which only that mapping exposes.
- `config/`, `cache/` and `dossier/` are mounted from the host, so your API key
  and the Instagram data you collect never end up baked into an image you might
  push somewhere.
- AI mode talks to an Ollama running on your **host**, via
  `OLLAMA_HOST=http://host.docker.internal:11434`. On Linux, run the container
  with `--network=host` or point that variable at your host's IP instead.

To set up the instagrapi backend from inside the container:

```bash
docker compose run --rm --entrypoint python osintgram scripts/instagrapi_login.py
```

---

## 3. Your first search

1. Type a username in **Target username** (with or without the `@`).
2. Leave the switch on **AI** and ask something in plain language, e.g.
   *"how many followers do they have and which hashtags do they use most?"*
3. Press **Run**.

The page shows a summary bar (requests spent, successes, failures, cache hits,
elapsed time), the model's written answer — which fills in word by word as the
model writes it — and one result card per command it ran. If you'd rather watch it work, tick **"Verbose mode"** before running:
you then see each command start and finish, and every single backend request as
it happens.

Nothing is downloaded to your disk unless you explicitly export it.

---

## 4. The two modes: AI and Base

The switch in the top-right corner picks how commands get chosen. Your choice
is remembered in the browser.

### AI mode (purple)

You describe what you want; the local model decides which commands to run,
runs them, and writes a summary. Good when you don't know exactly what you're
looking for, or when one question spans several commands.

The model only ever picks from the same command list as Base mode — it cannot
invent new ones. The raw results are always shown to you in full underneath the
answer, so you can check what it actually found rather than trusting the prose.

**You can leave the target empty in AI mode.** With no username set, the model
is given only the two searches that belong to no account (hashtag and place),
and told so — useful for *"recent posts tagged #milano"*. No request is spent
resolving a target that nothing needs.

### Base mode (teal)

No model involved, and no Ollama required. Every command is listed and you tick
the ones you want, setting their parameters yourself.

The picker is built to be scanned rather than scrolled: one line per command,
three columns, with the description in the tooltip. Groups fold away and each
shows how many of its commands are selected (`2/7`), so a collapsed group still
tells you whether something inside it will run. Which groups are open is
remembered between restarts.

- **Search box** — filters every group at once, by name or description, so you
  don't have to remember which group a command lives in. Groups open
  automatically while you type and go back to how you left them when you clear
  it.
- **⚙ on a row** — that command has parameters. They appear underneath once you
  select it.
- **Empty parameter field** — uses the command's own default. **`all`**
  removes the limit entirely (available only on numeric caps).

Selected commands run **in the order shown on screen**, each producing its own
result card.

"Request limit", "Cache lifetime" and "Verbose mode" work identically in
both modes.

---

## 5. What you can ask for

28 commands, grouped by what they tell you. Parameters are in `code`.

### Profile

| Command | What you get | Cost |
|---|---|---|
| **Profile info** | Bio and **all bio links**, follower/following/post counts, business & verified flags, category, pronouns, public email/phone, full business address including coordinates, linked Facebook id, reel and tag counters | free¹ |
| **Account info** | Instagram's *About this account*: country of registration, creation month, number of username changes | 1 |
| **Profile picture** | Direct CDN URL at full resolution | free¹ |
| **Stories** | Currently active stories, previewed vertically | 2 |
| **Story highlights** | Pinned story highlights: title, count, cover | 2 |
| **Photos** | Direct CDN URLs of posted photos — `limit` | per page |

¹ Read from the profile lookup the run already performs.

> **On "Account info":** two limits come from Instagram, not from this
> tool. The creation date has month precision (`January 2020`, no day), and
> username changes are reported only as a **count** — the panel never says what
> the old usernames were, so nothing can show them.

### Network

| Command | What you get | Parameters |
|---|---|---|
| **Followers** / **Following** | The accounts, with id, username, full name | `limit` (200) |
| **Suggested profiles** | Accounts Instagram suggests as related — often the real circle or alternate accounts (HikerAPI only) | |
| **Compare profiles** | Connections in common with another account: who follows both, who both follow | `other_username`, `scope` (`both`/`followers`/`followings`), `limit` (500) |
| **Who tagged** | Accounts that tagged the target in their own posts | `limit` |
| **Tagged by target** | Accounts the target tagged | `limit_posts` |
| **Who commented** | Accounts that commented, ranked by how often | `limit_posts` |

`scope` on **Compare profiles** is worth knowing: a one-sided comparison costs
half the requests of `both`.

### Content

| Command | What you get |
|---|---|
| **Hashtags** | Hashtags used, most frequent first |
| **Captions** | Post captions |
| **Addresses** | Geotagged locations, reverse-geocoded, **plotted on a map** |
| **Comments** | Every comment with author and post |
| **Like totals** / **Comment totals** | Total, min, max, average — plus post previews |
| **Media types** | How many posts are photos, videos, carousels, with views, collaborations and paid partnerships |
| **Posting times** | Weekday × hour heatmap of when they post, and how often |
| **Photo descriptions** | Alt text of each photo, carousel slides included |

All of these take `limit_posts`.

> **On "Photo descriptions":** Instagram only returns alt text the author wrote
> themselves — its automatic "May be an image of…" descriptions are no longer
> exposed. On most accounts it comes back empty; the card then tells you how
> many photos were checked, so you know it looked rather than failed.

### Contacts

**Follower emails**, **Following emails**, **Follower phones** and
**Following phones** — public email addresses and phone numbers among the
target's followers or followings. Parameters `match_limit` (20) and
`max_checks` (100).

These are **the most expensive commands in the tool**: they spend one extra
request per account examined, because a contact field can only be read from a
full profile lookup. See [Keeping the cost down](#6-keeping-the-cost-down).

### Searches that need no target

| Command | What you get | Parameters |
|---|---|---|
| **Hashtag search** | Posts published with a hashtag, and who posted them | `hashtag`, `sort` (`top`/`recent`), `limit` (30) |
| **Place search** | Recent posts from a place, searched by name, with the matched place and its alternatives | `place`, `limit` (30) |

With only these selected the username field stops being required, and the label
says so.

---

## 6. Keeping the cost down

Ollama is local and free. The Instagram backend is the part with a real budget
— HikerAPI's paid quota, or instagrapi's account-risk exposure. Six things
help, and they compose.

### Know what's left

The title bar shows **your remaining HikerAPI credit**, refreshed after every
search. Checking it is free — HikerAPI doesn't bill that lookup.

### Price it before you run it

In Base mode, **"≈ Estimate requests"** prices the selected commands before you
spend anything:

```
≈ 116–126 requests · 474 available
```

Hover for the per-command breakdown — that's how you spot the expensive one. It
warns you when the estimate exceeds your credit. The estimate is derived from
the same pagination rules the commands use plus the target's own counters, so
it costs one profile lookup the run itself would have spent anyway (and which
the cache then serves).

Estimates are ranges, never promises: page sizes vary, and cache hits are free.

### Cache

Every **individual** backend request is cached — not whole command results.
That granularity is the point: two different commands, two different questions,
even two different target accounts that happen to need the same underlying
lookup all share one hit.

- Default lifetime `HIKER_CACHE_TTL` (300 s). The **"Cache lifetime"** pills
  override it per search: `1 hour`, `6 hours`, `24 hours` for a long session on one
  account, or `Off` to force everything fresh.
- Each entry keeps the lifetime it was saved with, so changing the setting
  never retroactively expires what you already have.
- Stored on disk (`cache/requests.sqlite3`), so it survives restarts instead of
  being paid for twice. **"Clear cache"** empties it.
- **Errors are never cached**, so a momentary failure doesn't get stuck for the
  whole lifetime.

In verbose mode a cache hit shows as `♻️ … from cache` and does **not** count
towards the request total — nothing was sent.

### Cap the whole run

The **"Request limit"** pills (`10`/`50`/`100`) cap real requests for the
entire search, not per command: a search calling three commands still spends at
most that many in total.

When the cap is reached mid-scan the command **doesn't fail** — it returns what
it already found, a shorter list rather than an error. Verbose mode logs a
`⏸️ … request limit reached` line for each skipped request.

Cache hits are free and never count against it, so a scan can examine more
accounts than the limit if enough of them were already cached.

### Stop it

**"⏹ Stop"** stops the run **on the server**, not just in the browser —
without that, cancelling the page's request would leave the worker running, and
spending, to the end. Closing the tab stops it too.

### Momentary failures are retried, not paid twice

A dropped connection, a read timeout or a `429`/`5xx` is retried (3 attempts by
default, with a growing pause) instead of ending a scan with half its results.
Only failures that look transient are retried — "user not found" is answered
once. Every attempt is a real request and counts towards the total and the cap;
verbose mode shows a `🔁 … retrying` line.

Tune with `HIKER_RETRY_ATTEMPTS` (`1` disables retrying) and
`HIKER_RETRY_DELAY`.

---

## 7. Reading the results

Each command gets its own card, rendered for what it actually is: user lists as
rows, hashtags as pills, addresses on a map, posting times as a heatmap.

- **Post previews** — "Tipo media", "Totale like" and "Totale commenti" show
  their numbers plus a collapsed **"Post previews"** grid. Open it for
  thumbnails, filterable by photo/video/carousel, with likes and comments on
  each. Clicking a photo or video opens the **original file** straight from
  Instagram's CDN — no instagram.com page in between. Carousels expand into
  their slides. Hover a tile for its caption, co-authors and audio track.
  Thumbnails load only when you open the section, and preview data is never
  sent to the AI model.
- **Map** — "Addresses" plots geotagged locations (Leaflet + OpenStreetMap,
  loaded only when you open it). Each address also has a 📍 link to
  OpenStreetMap.
- **Filter box** — long lists (followers, comments, captions) get one once they
  pass a dozen rows.
- **Numbers and ids** — figures are always shown in full, never abbreviated:
  an Instagram id rendered as "5B" would be useless. Identifiers (the account
  id, a linked Facebook id, a location id) carry no thousands separators
  either, so they can be copied out as-is; clicking one selects the whole
  value. Where a number is rounded for want of room — the counts on post
  thumbnails — the exact figure is in the tooltip.
- **Raw JSON** — every card can show the exact response it was built from.

### Search history

Click the **Target username** field for your recent targets; in AI mode, click
the **Request** field for your recent questions. Both filter as you type;
arrow keys and Enter pick one, `×` or Shift+Delete removes one.

A target is recorded only once it actually resolved to a real account. Stored
in `config/search_history.json` and `config/query_history.json`, so they
survive restarts.

---

## 8. Saving, comparing, exporting

### Dossier — save a search and see what changed later

**"💾 Save dossier"** stores a finished search on the server, under
`dossier/<target>/`. The **"Saved dossiers"** panel lists the ones for the
username in the box:

- **Open** replays a saved run **without spending a single request**.
- **"What changed"** compares it with a later run of the same target: new
  and lost followers, an edited bio, changed counters.

Volatile things — signed CDN URLs, which rotate constantly — are left out of
the comparison, so it reports real changes only.

### Export

| Button | What you get |
|---|---|
| **⬇ JSON** | The card's full result |
| **⬇ CSV** | The same as a table — comma separated with a BOM, so Excel reads it as UTF-8 |
| **⬇ Media (N)** | The original photos and videos, as one zip |
| **⬇ Export all** | Request, answer and every result in one JSON file |
| **📄 Report** | The whole search as a standalone HTML page |

**CSV safety:** any text starting with `=`, `+`, `-` or `@` is prefixed with
`'`, so a spreadsheet can't execute it as a formula.

**Media zip:** only Instagram's own CDN hosts are fetched — the URL list comes
from the page, so it's treated as untrusted input. At most 100 files and
300 MB; anything that can't be fetched is listed in `errori.txt` inside the
archive rather than failing the whole download.

**Report** is the one to hand to someone else. It's a single HTML file that
opens in any browser with no server and no Osintgram: a header with target,
mode, request, backend and timestamps, every result card exactly as you
reviewed it (previews expanded, raw JSON folded into a "Raw data" section),
and the disclaimer. Interactive controls are stripped; addresses keep their
OpenStreetMap links.

> Image previews in the report point at Instagram's CDN with **signed URLs that
> expire after a few hours**. Use "⬇ Media" to keep the files themselves — all
> text and numbers in the report are permanent.

Both the report and the app page carry a print stylesheet, so `Ctrl`/`Cmd`+`P`
→ *Save as PDF* gives a clean document without the form, buttons or progress
log.

---

## 9. Configuration reference

All optional; everything has a working default.

### Backend

| Variable | Default | What it does |
|---|---|---|
| `HIKERAPI_TOKEN` | — | HikerAPI key. Wins over the UI and the config file |
| `INSTAGRAM_BACKEND` | auto | Force `hikerapi` or `instagrapi` |
| `INSTAGRAM_USERNAME` / `INSTAGRAM_PASSWORD` | — | instagrapi credentials |

Auto-selection prefers HikerAPI when a key is configured, and falls back to
instagrapi when a saved session exists.

### Cost and reliability

| Variable | Default | What it does |
|---|---|---|
| `HIKER_CACHE_TTL` | `300` | Default cache lifetime in seconds; `0` disables caching |
| `HIKER_CACHE_PATH` | `cache/requests.sqlite3` | Cache file; empty string = memory only |
| `HIKER_RETRY_ATTEMPTS` | `3` | Attempts per request; `1` disables retrying |
| `HIKER_RETRY_DELAY` | `0.6` | Seconds before the first retry, growing after each |
| `HIKER_CONTACT_MAX_CHECKS` | `100` | Ceiling on accounts examined by the contact commands |

### AI mode

| Variable | Default | What it does |
|---|---|---|
| `OLLAMA_MODEL` | `llama3.1:8b` | Any tool-calling capable model you've pulled |
| `OLLAMA_MAX_TOKENS` | `1024` | Cap on the model's reply length |
| `OLLAMA_NUM_CTX` | `16384` | Context window. Ollama defaults to 4096 regardless of what the model supports, which is not enough here — see below |
| `OLLAMA_TEMPERATURE` | `0.1` | Low on purpose: picking a tool is a decision, not a creative act |
| `OLLAMA_HOST` | `http://127.0.0.1:11434` | Where Ollama is listening. Read by the Ollama client itself; the Docker setup points it at your host |

---

## 10. Troubleshooting

**"A target username is required"** — a selected command needs an account. Either
type one, or select only the hashtag/place searches.

**A key pasted in the UI seems ignored** — `HIKERAPI_TOKEN` is set and takes
precedence. The panel says so; unset the variable and restart, or change the
variable instead.

**"Key rejected by HikerAPI"** — the key was checked before being accepted
and HikerAPI refused it. The message is HikerAPI's own; nothing was saved.

**"The key can only be set from localhost" (403)** — the key endpoints only
answer to `127.0.0.1`. Reach the page at `http://127.0.0.1:8000`, not through
another hostname.

**AI mode does nothing / answers without running commands** — Ollama isn't
running (`ollama serve`), the model isn't pulled (`ollama pull llama3.1:8b`),
or the model doesn't support tool calling. Base mode works meanwhile.

**"Photo descriptions" comes back empty** — expected on most accounts; see the
note in [What you can ask for](#content).

**"Suggested profiles" / "Account info" refuse to run** — you're on the
instagrapi backend; these two are HikerAPI only.

**A private profile** — most commands need a public one and say so explicitly
rather than returning nothing.

**"attempt to write a readonly database"** — the cache file isn't writable.
Fix its permissions, or set `HIKER_CACHE_PATH=""` to run from memory.

**Results look stale** — set "Cache lifetime" to `Off` for a fresh run,
or press "Clear cache".

---

## 11. What it stores on disk

| Path | What | Git-ignored |
|---|---|---|
| `config/credentials.ini` | HikerAPI key, instagrapi credentials | yes |
| `config/instagrapi_session.json` | Saved instagrapi session | yes |
| `config/search_history.json` | Recent target usernames | yes |
| `config/query_history.json` | Recent AI requests | yes |
| `cache/requests.sqlite3` | Cached backend responses | yes |
| `dossier/<target>/` | Saved searches | yes |

Nothing else is written unless you export it yourself. Result pages are served
with `Cache-Control: no-store`, so OSINT results don't linger in the browser's
disk cache.

Everything under `config/` is git-ignored — only `config/credentials.ini.example`
is tracked — so a clone can't commit your key by accident. If one has been
exposed anyway, **rotate it at the provider**: deleting the file isn't enough,
git history keeps it.

---

## Disclaimer

FOR EDUCATIONAL PURPOSE ONLY. The contributors do not assume any
responsibility for the use of this tool.

Results can contain third parties' personal data: handle them in accordance
with data-protection law (GDPR and equivalents) and Instagram's Terms of Use.
Don't use your main or personal Instagram account with this tool.
