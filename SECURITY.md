# Security Policy

This is an unofficial, personal-use tool that processes your own Garmin Connect
health data locally. It is not affiliated with Garmin Ltd.

## Reporting a vulnerability

If you discover a security issue, please **do not open a public issue**. Instead,
email the maintainer at **hiroshi.yamaki@gmail.com** with:

- a description of the issue and its impact,
- steps to reproduce, and
- any relevant logs (with personal data redacted).

You can expect an acknowledgement within a reasonable time. As a personal
project there is no formal SLA, but reports are taken seriously.

## Handling personal data

This tool reads personal health data (weight, GPS routes, heart rate, etc.).
To keep it private:

- **Never commit personal data.** `data/`, `result/`, and `.env` are git-ignored.
  Keep them outside the repository (see `GARMIN_DATA_DIR` / `GARMIN_RESULT_DIR`).
- **Never commit credentials.** `GARMIN_EMAIL` / `GARMIN_PASSWORD` belong in your
  local `.env` only. OAuth tokens are cached under `GARMINTOKENS` (default
  `~/.garth`), also outside the repo.
- If personal data is ever committed by accident, rewrite history (e.g. with BFG
  or `git filter-repo`) before pushing, and rotate any exposed credentials.

## Scope

Use at your own risk. Comply with Garmin's Terms of Service. The authors assume
no liability for issues arising from use of this software.
