# Changelog

## 2.0

The tool is now a **local web application**. The interactive shell is no longer
the documented way to use Osintgram - see [`doc/web-ui.md`](web-ui.md).

**New: the web interface**
- Web UI (FastAPI + a single-page frontend) served on `127.0.0.1`, with a
  terminal-style header, light/dark support and a print stylesheet.
- **AI mode**: describe a request in plain language and a local model (via
  [Ollama](https://ollama.com)) picks which lookups to run and summarizes the
  answer. No external LLM key - the model runs on your machine. Works with no
  target set, restricted to the searches that belong to no account.
- **Base mode**: all 28 commands listed, grouped, searchable and collapsible,
  with their parameters set directly. No model required.
- Live progress ("Verbose mode"): every command and every single backend
  request reported as it happens.

**New: analyses**
- "Account info" - Instagram's *About this account*: country of
  registration, creation date, number of username changes.
- "Posting times" - weekday x hour posting heatmap and frequency.
- "Compare profiles" - mutual connections between two accounts, on followers,
  followings or both.
- "Story highlights" and "Suggested profiles".
- "Hashtag search" and "Place search" - searches that need no target.
- "Profile info" now returns everything the profile object carries: bio links,
  pronouns, category, public phone with country code, full business address
  with coordinates, linked Facebook id, reel/tag counters.
- Post previews (filterable grid, direct CDN links, carousel slides, views,
  collaborations, paid partnerships, audio) on every post summary.
- Geotagged locations plotted on a map.

**New: cost control**
- Per-request cache, shared across commands and targets, persisted to
  `cache/requests.sqlite3`; errors are never cached.
- "Estimate requests" - prices a selection before running it.
- Remaining HikerAPI credit in the header (free lookup).
- "Request limit" - a hard cap on real requests for a whole run; commands
  return partial results instead of failing when it's reached.
- "Stop" - cancels a run on the server, not just in the browser.
- Automatic retry with backoff on transient failures (timeouts, 429, 5xx).

**New: saving and sharing**
- Dossier: save a finished search, reopen it without spending a request, and
  diff it against a later run of the same target.
- Export per card (JSON, CSV with Excel-safe escaping) or the whole search.
- Media zip of the original photos and videos.
- Standalone HTML report of an entire search.
- Search history for targets and AI requests, persisted across restarts.

**New: configuration**
- HikerAPI key can be pasted into the UI: verified before it's accepted, and
  optionally saved to `config/credentials.ini`, the same file the CLI reads.
- Alternative **instagrapi** backend (`INSTAGRAM_BACKEND`), reaching feature
  parity with HikerAPI except "Suggested profiles" and "Account info".

**Bug fixes**
- Migrated off HikerAPI endpoints deprecated in `hikerapi` 1.8 (`user_medias_v2`,
  `user_followers_v2`, `user_following_v2`) to the current g2 ones.
- `tagged`: HikerAPI returns `usertags` as `{"in": [...]}`, which was being
  iterated as a list - no tagged users were ever found.
- `photos`: photos were detected by the presence of `image_versions2`, which
  every post has on the g2 endpoints; now uses `media_type`.
- `mediatype`: carousels were counted as neither photos nor videos.

**Removed**
- The interactive shell and its command-line entry point (`main.py`,
  `src/Osintgram.py`, `src/hikercli.py`, `src/config.py`,
  `src/printcolors.py`, `doc/COMMANDS.md`). Everything they did is in the web
  UI, which reaches further; keeping two implementations of the same lookups
  meant fixing every bug twice.
- With them go five dependencies (`instagram-private-api`, `prettytable`,
  `requests-toolbelt`, `gnureadline`, `pyreadline`). `pyreadline==2.1` is
  broken on Python 3.10+, so `pip install -r requirements.txt` used to fail
  outright on modern Windows - it now installs everywhere.

**Packaging**
- `config/credentials.ini` is no longer tracked by git: `config/credentials.ini.example`
  is the template to copy. Previously a clone could commit its own API key by
  accident.
- Docker now serves the web app instead of the removed shell, as a non-root
  user, published on `127.0.0.1` only, with `config/`, `cache/` and `dossier/`
  mounted from the host so no key or collected data is baked into the image.
- CI actually runs the test suite (it used to swallow failures), on Python 3.10
  and 3.13.
- Minimum Python is **3.10**, the floor FastAPI and uvicorn require - the
  previous "3.9+" claim was wrong.

**Internals**
- New `src/osint_service.py`: a side-effect-free service layer (no printing, no
  file writing, no `input()`) that both the web app and new code build on.
- `pytest` suite (125 tests) running entirely on synthetic fixtures - no API
  key, quota or network - including tests that keep the documentation in sync
  with the code.

## [1.3](https://github.com/Datalux/Osintgram/releases/tag/1.3)
**Enhancements**
- Artwork refactoring (#149) 
- Added command line mode (#155)
- Added output limiter (#201)

**Bug fixes**
- Losing collected data (#156)
- JSON user info (#202)
- Issue #198 (#200)
- Issue #204 (12e730e)


## [1.2](https://github.com/Datalux/Osintgram/releases/tag/1.2)
**Enhancements**
- Added virtual environment (#126)
- Removed some typos (#129, #118)
- Added new configuration (#125)
- Added new `commentdata` command (#131) 
- Added Docker support (#141) 


**Bug fixes**
- Fix bug  #138 (fc2a6be)
- SSL certificate error (#136) 


## [1.1](https://github.com/Datalux/Osintgram/releases/tag/1.1)
**Enhancements**
- Improved command parser (#86)
- Improved errors handling (8bd1abc)
- Add new line when input command is empty (f5211eb)
- Added new commands to catch phone number of users (#111)
- Added support for Windows (#100)


**Bug fixes**
- Fix commands output limit bug (#87)
- Fix setting target with "." in username (9082990)
- Readline installing error (#94 )


## [1.0.1](https://github.com/Datalux/Osintgram/releases/tag/1.0.1)
**Bug fixes**
- Set itself as target by param

## [1.0](https://github.com/Datalux/Osintgram/releases/tag/1.0)
**Enhancements**
- Set itself as target (#53)
-  Get others info from user (`info` command):
  - Whats'App number (if available)
  - City Name (if available)
  - Address Street (if available)
  - Contact phone number (if available)

**Bug fixes**
- Fix login issue (#79, #80, #81)

## [0.9](https://github.com/Datalux/Osintgram/releases/tag/0.9)

**Enhancements**
- Send a follow request if user not following target (#44)
- Added new `fwingsemail` command (#50)
- Added autocomplete with TAB (07e0fe8)

**Bug fixes**
- Decoding error of response [bug #46]  (f9c5f73)
- `stories` command not working (#49)

## [0.8](https://github.com/Datalux/Osintgram/releases/tag/0.8)

**Enhancements**
- Added `wtagged` command (#38)
- Added `fwersemail` command (#40)
- Access private profiles if you following targets (#37)
- Added more info in `info` command (#36)


**Bug fixes**
- Minor bug fix in `addrs` commands (9b9086a)

## [0.7](https://github.com/Datalux/Osintgram/releases/tag/0.7)

**Enhancements**
- banner now show target ID (#30) 
- persistent login (#33)
- error handler (85e390b)
- added CTRL+C handler (c2c3c3e)

**Bug fixes**
- fix likes and comments posts counter bug (44b7534)



## [0.6](https://github.com/Datalux/Osintgram/releases/tag/0.6)

**Enhancements**

- new `wcommented` command (#27)
- new `target` command
- added json dump also for captions command
- added options as arguments (#24)
- new Instagram APIs (#26)

**Bug fixes**

- fix empty addrs bug (#12)


## [0.5](https://github.com/Datalux/Osintgram/releases/tag/0.5)

**Enhancements**

- added JSON export feature

**Bug fixes**

- Fix #2

## [0.4](https://github.com/Datalux/Osintgram/releases/tag/0.4)

**Enhancements**

- added `stories` command (#8)
- added `target` command (#9)

**Bug fixes**

- added a check if the target has a private profile to avoid tool crash (#10)
- fixed `tagged` bug (#5)

## [0.3](https://github.com/Datalux/Osintgram/releases/tag/0.3)

**Enhancements**

- added `photos` command
- added `captions` command
- added `mediatype` command
- added `propic` command

## 0.2

**Enhancements**

- write in file the output of commands

## 0.1

**Initial release** 


