# TOOLS.md - Local Notes

Skills define _how_ tools work. This file is for _your_ specifics — the stuff that's unique to your setup.

## What Goes Here

Things like:

- Camera names and locations
- SSH hosts and aliases
- Preferred voices for TTS
- Speaker/room names
- Device nicknames
- Anything environment-specific

## Examples

```markdown
### Cameras

- living-room → Main area, 180° wide angle
- front-door → Entrance, motion-triggered

### SSH

- home-server → 192.168.1.100, user: admin

### TTS

- Preferred voice: "Nova" (warm, slightly British)
- Default speaker: Kitchen HomePod
```

## Why Separate?

Skills are shared. Your setup is yours. Keeping them apart means you can update skills without losing your notes, and share skills without leaking your infrastructure.

---

Add whatever helps you do your job. This is your cheat sheet.

### Bird / X list shortcuts

- `ct` → `https://x.com/i/lists/1933193197817135501`
- For X/Twitter pulls: **use Bird CLI by default** (avoid scraping/browser extraction unless explicitly requested).
- Preferred output format for list pulls:
  - one item per paragraph (blank line between items)
  - each line: `<post text> @<authorUsername>`

### Web scraping fallback order

Use this order for web extraction/scraping:
1. API / `curl` / `web_fetch`
2. `summarize` (especially for articles/videos/transcripts)
3. `Scrapling` fallback for anti-bot/challenge pages
4. Full browser automation only when interaction/login is required

### Perplexity Finance (company research)

- For company snapshots (overview, financials, earnings, holders, analysis), use Perplexity Finance pages first:
  - `https://www.perplexity.ai/finance/<TICKER>` (e.g., `TSLA`)
- If `web_fetch` is blocked/challenged, use browser automation to read tabs (`Overview`, `Financials`, `Earnings`, etc.).
- For Market Summary on `/finance`, expand all accordion items before summarizing.
- When needed, follow with deeper source verification (filings/transcripts/news) on request.

### Camoufox vs Scrapling (when to use)

- **Camoufox**
  - Use for stealth browser sessions where browser fingerprinting/anti-bot resistance matters.
  - Best when you need browser-like behavior and session realism.
  - Not the default for simple extraction.

- **Scrapling**
  - Use as scraping framework fallback when normal tools fail on anti-bot/challenge pages.
  - Best for extraction pipelines (fetch + parse + selectors/crawling).
  - Prefer before full manual browser automation when interaction is not required.

Decision rule:
- If you need data extraction only: try normal flow, then **Scrapling**.
- If you need high-stealth browser behavior/session realism: use **Camoufox**.
- If you need clicks/logins/multi-step UI interaction: use browser automation.

### SSH (m4mini)

- host: `m4mini`
- user: `plutusclawdbot`
- primary LAN IP: `192.168.1.240` (en0)
- alt LAN IP: `192.168.1.31` (en1)
- quick connect: `ssh plutusclawdbot@192.168.1.240`

### Setup Snapshot

- GitHub account: `plutusclawdbot`
- Workspace repo: `https://github.com/plutusclawdbot/openclaw-workspace`
- Auth flow: `gh auth login -h github.com -p https -w`
- Core tooling in use: `gh`, `git`, `bird`, OpenClaw
- Secrets policy: keep API keys/tokens in local env/config only (never in repo)
