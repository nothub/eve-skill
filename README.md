# eve-data

A Claude Code skill for querying EVE Online data: [ESI](https://esi.evetech.net), a local copy of
the Static Data Export, [Fuzzwork](https://market.fuzzwork.co.uk) market aggregates, and
[zKillboard](https://zkillboard.com).

All four sources are public. No API key, no character login. Character-private data (skills,
wallet, assets, colonies) needs an authenticated ESI session and is out of scope.

The skill itself is `SKILL.md`. Everything below is setup.

## Install

Drop it anywhere Claude Code looks for skills. As a submodule:

```sh
git submodule add git@github.com:nothub/eve-skill.git .claude/skills/eve-data
```

Or globally, for every project:

```sh
git clone git@github.com:nothub/eve-skill.git ~/.claude/skills/eve-data
```

## Configure

Two environment variables.

| variable | meaning | default |
|---|---|---|
| `EVE_SDE_DB` | path to the SDE SQLite file | `${XDG_DATA_HOME:-$HOME/.local/share}/eve-sde/sde.db` |
| `EVE_ESI_UA` | User-Agent with a contact address | none, the skill asks |

CCP requires a User-Agent that identifies who you are, and uses it to contact you when a script
misbehaves. A made-up address gets your traffic blocked instead of warned, so set a real one:

```sh
export EVE_ESI_UA='myapp/1.0 (me@example.com)'
```

## Static data

The SDE answers most "which / where / how many jumps" questions offline, with no rate limit.
About 475 MB unpacked. Download it once, refresh when a patch changes items or the map:

```sh
SDE="${EVE_SDE_DB:-${XDG_DATA_HOME:-$HOME/.local/share}/eve-sde/sde.db}"
mkdir -p "$(dirname "$SDE")"
curl -o "$SDE.gz" https://www.fuzzwork.co.uk/dump/latest-sqlite.db.gz
gunzip -f "$SDE.gz"
```

Thanks to [Steve Ronuken](https://www.fuzzwork.co.uk) for maintaining the conversion and the
market API.

## Requirements

`curl`, `jq`, `sqlite3`.
