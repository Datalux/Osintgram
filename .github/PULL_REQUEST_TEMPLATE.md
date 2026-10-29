<!--
Thanks for contributing! Please open this pull request against the
`development` branch, not `master`. `master` only receives tested releases.
If the base branch shown above is `master`, change it before submitting.
-->

## What does this change?

<!-- A short description. Link the issue it fixes, if any: "Fixes #123". -->

## Why?

<!-- The problem it solves or the use case it adds. -->

## Type of change

- [ ] Bug fix
- [ ] New feature or command
- [ ] Documentation only
- [ ] Refactor / maintenance

## Checklist

- [ ] The base branch is `development`.
- [ ] `python -m pytest` passes, and new behavior has tests (including the unhappy path: bad input, errors, empty results).
- [ ] `flake8 . --select=E9,F63,F7,F82` reports nothing (this is what CI runs).
- [ ] Files are read and written as UTF-8 (`encoding="utf-8"`), so the tests also pass on Windows.
- [ ] If a command was added or removed, `doc/web-ui.md` is updated, including the "N commands" line (a test checks it).
- [ ] New settings, environment variables or `credentials.ini` options are documented.
- [ ] No secrets, tokens or real personal data in the code, tests or screenshots.

## Cost and privacy

<!--
Osintgram talks to paid APIs and handles third parties' data. Please say:
- How many backend requests one run of this feature makes, and whether the
  input has an upper limit (so a model or a typo can't trigger thousands).
- Where any data is sent or stored (third-party services, files on disk), and
  whether it is off by default.
- Which results are estimates or heuristics rather than facts, and how the UI
  makes that clear.
Write "Not applicable" if none of this applies.
-->

## Screenshots (UI changes)

<!-- Before / after, if the web interface changes. -->
