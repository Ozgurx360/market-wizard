# Market Wizard — a Claude Code plugin

Personal Claude Code plugin: trading-strategy & options skills for an Interactive Brokers workflow.

## Skills
- **`market-wizard:leaps`** — full-lifecycle long-call LEAPS: evaluate new entries; review existing positions
  for HOLD / ROLL-OUT / ROLL-UP / ROLL-DOWN / TRIM / CLOSE; single calls **and** call debit spreads; always
  shows intrinsic vs extrinsic value + the relevant Greeks. Read-only by default; **all order placement needs
  explicit human approval.** Account is read from your CLAUDE.md/memory — it asks if not configured.
- _planned:_ `market-wizard:csp` (cash-secured puts), `market-wizard:cc` (covered calls).

## Install
```
/plugin marketplace add Ozgurx360/market-wizard
/plugin install market-wizard@market-wizard
```
Then `/help` → `/market-wizard:leaps`.

## Update (after a push)
```
/plugin marketplace update market-wizard && /reload-plugins
```
No version pin — every push is the latest.

## Add a skill later
Drop `plugins/market-wizard/skills/<name>/SKILL.md`, commit, push, `/reload-plugins` → auto-loads as `market-wizard:<name>`.

## Layout
```
.claude-plugin/marketplace.json          marketplace catalog
plugins/market-wizard/
  .claude-plugin/plugin.json             plugin manifest
  skills/leaps/SKILL.md                  the LEAPS skill
```
