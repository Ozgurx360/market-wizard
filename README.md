# Finance — a Claude Code plugin

Personal Claude Code plugin: trading-strategy & options skills for an Interactive Brokers workflow.

## Skills
- **`finance:leaps`** — full-lifecycle long-call LEAPS: evaluate new entries; review existing positions for
  HOLD / ROLL-OUT / ROLL-UP / ROLL-DOWN / TRIM / CLOSE; single calls **and** call debit spreads; always shows
  intrinsic vs extrinsic value + the relevant Greeks. Read-only by default; **all order placement needs
  explicit human approval.**
- _planned:_ `finance:csp` (cash-secured puts), `finance:cc` (covered calls).

## Install
```
/plugin marketplace add Ozgurx360/finance
/plugin install finance@finance-tools
```
Then `/help` → `/finance:leaps`.

## Update (after a push)
```
/plugin marketplace update finance-tools && /reload-plugins
```
No version pin — every push is the latest.

## Add a skill later
Drop `plugins/finance/skills/<name>/SKILL.md`, commit, push, `/reload-plugins` → it auto-loads as `finance:<name>`.

## Layout
```
.claude-plugin/marketplace.json     marketplace catalog (lists the finance plugin)
plugins/finance/
  .claude-plugin/plugin.json        plugin manifest
  skills/leaps/SKILL.md             the LEAPS skill
```
