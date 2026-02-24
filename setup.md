# Setup.md — Plutus GitHub Setup

Last updated: 2026-02-20
GitHub account: **plutusclawdbot**

## 1) GitHub Repositories

- `setup` (this repo): https://github.com/plutusclawdbot/setup
- `market-brief`: https://github.com/plutusclawdbot/market-brief
- `soul`: https://github.com/plutusclawdbot/soul

## 2) Auth & Access Model

- GitHub CLI is used for auth and repo operations.
- Auth method: `gh auth login -h github.com -p https -w`
- Current active account used in terminal: `plutusclawdbot`
- Pushes are done via authenticated `gh`/git HTTPS flow.

## 3) Repo Purpose

### `market-brief`
Contains the briefing framework in `brief.md` and generated market briefs.

Current framework includes sections for:
- Executive snapshot
- Regime + cross-asset read
- Polymarket signal check
- CT (Crypto Twitter) sentiment scan (200 posts)
- Week-ahead pending economic indicators
- Podcast signal check (starting with All-In)
- Earnings transcript signal analysis
- Bottom-line portfolio scenarios

### `soul`
Identity/persona-related content and operating style references.

### `setup`
This documentation repo for reproducible setup state.

## 4) Tools Installed / Configured by Erlin

- **OpenClaw**: `2026.2.19-2` (updated)
- **GitHub CLI (`gh`)**: `2.86.0` (authenticated as `plutusclawdbot`)
- **Bird CLI** (from `fightingentropy/bird`): `0.8.0 (6e88ffd4)`
- **Camoufox** Python package: `0.4.11`
  - Installed in venv: `~/.openclaw/workspace/.venvs/camoufox`

## 5) Tooling Used in Workflow

- `gh` CLI (repo create/list/push)
- git (commit/push content changes)
- `bird` CLI for CT/X list pulls
- Camoufox (available for stealth browser automation workflows)
- market data pull scripts (Finnhub + other public endpoints)

## 6) Reproduce This Setup (Quickstart)

```bash
# 1) Authenticate GitHub CLI
gh auth login -h github.com -p https -w

# 2) Verify
gh auth status

# 3) Clone repos
git clone https://github.com/plutusclawdbot/market-brief.git
git clone https://github.com/plutusclawdbot/soul.git
git clone https://github.com/plutusclawdbot/setup.git
```

## 7) Notes

- No secrets/tokens are stored in this repo.
- API keys should stay in local environment/config only.
