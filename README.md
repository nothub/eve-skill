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

Three environment variables, all optional. It works out of the box without them.

| variable | meaning | default |
|---|---|---|
| `EVE_SDE_DB` | path to the SDE SQLite file | `${XDG_DATA_HOME:-$HOME/.local/share}/eve-sde/sde.db` |
| `EVE_ESI_UA` | product token in the User-Agent | `eve-notes/1.0` |
| `EVE_ESI_CONTACT` | contact address appended in parentheses | omitted |

CCP asks for a User-Agent that identifies the caller, and uses it to reach you when a script
misbehaves. Requests work without a contact address, but nobody can warn you before throttling,
so set one if you use this more than occasionally:

```sh
export EVE_ESI_CONTACT='me@example.com'
```

The default product token is deliberately dull. `eve-notes/1.0` says a small personal tool is
calling, which is all an API operator needs to know. Naming the agent or harness behind it invites
different handling and tells everyone downstream more than the request requires.

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
