# Security policy

## Reporting a vulnerability

**Please don't open a public issue for a security problem.**

Use GitHub's private reporting instead: go to the repository's **Security** tab
→ **Report a vulnerability**. That opens a private advisory only the maintainers
can see, and it lets us work on a fix before anything is public.

Useful things to include: what version or commit you tested, how to reproduce
it, and what an attacker would gain. A proof of concept helps a lot. If you're
not sure whether something counts, report it anyway — deciding that is our job,
not yours.

Please don't test against accounts or infrastructure you don't own, and don't
include other people's personal data in a report.

## Supported versions

This is a small project with one active line. Fixes land on the default branch;
there are no backports to older tags.

| Version | Supported |
|---|---|
| 2.x (web UI) | ✅ |
| 1.x (the old interactive shell) | ❌ removed in 2.0 |

## Design decisions that are not vulnerabilities

Some properties of this tool look alarming out of context but are deliberate
and documented. Reporting them is fine, but here's where we already stand:

**The web UI has no authentication.** It binds to `127.0.0.1` and is meant to
run on your own machine, like a development server. This is stated in the
README, in the guide and in the UI's own footer. "No login screen" is not a
finding; a way to reach it *from outside localhost* in a default install is.

The two endpoints that accept an API key (`POST`/`DELETE /api/token`)
additionally reject any request whose `Host` isn't localhost, or whose `Origin`
is external — that's the DNS-rebinding case, where a page you visit gets your
browser to talk to `127.0.0.1` as if it were same-origin. Every other endpoint
requires a JSON body, which a cross-origin request can't send without a CORS
preflight that never succeeds here.

**The tool collects other people's personal data.** That is what an OSINT tool
does. It only ever reads what a public Instagram profile already exposes, and
it cannot see private profiles. Handling the results lawfully is the user's
responsibility — see the disclaimer.

**Results are written to disk unencrypted** (`cache/`, `dossier/`), and the
API key is stored in `config/credentials.ini`. All three are git-ignored, and
the credentials file is written `0600`. Full-disk encryption is left to your
operating system.

## What is in scope

Things we would very much like to hear about:

- Any way to reach the app, or make it act, from outside `127.0.0.1` in a
  default install — CSRF, DNS rebinding, a hole in the `Host`/`Origin` check.
- Any way to read back a stored API key. Every endpoint is supposed to return
  only a masked preview (`hik_…9f2c`); the key itself should never come back
  out.
- Making the server fetch a URL of your choosing. The media download is
  restricted to `https` on `*.cdninstagram.com` and `*.fbcdn.net`, with caps on
  file count and total size, precisely because the URL list comes from the page
  and is treated as untrusted.
- Code execution or path traversal via profile data. Instagram content
  (usernames, captions, bios) is attacker-controlled as far as this tool is
  concerned: it is escaped before rendering, and text starting with `=`, `+`,
  `-` or `@` is prefixed with `'` in CSV exports so a spreadsheet can't run it
  as a formula.
- Anything that leaks results or credentials somewhere they shouldn't go —
  a request to a third party carrying data it has no business seeing.

## If you've exposed your own key

Push a `config/credentials.ini` with a real key in it, and deleting the file
isn't enough — git history keeps it, and anything pushed to a public repository
should be considered compromised immediately.

**Rotate the key at the provider** (HikerAPI, or change the Instagram password
for the instagrapi backend). Rewriting history is secondary and optional; the
rotation is what actually closes the exposure.
