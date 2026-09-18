---
name: eve-data
description: Query live and static EVE Online data with curl and sqlite3 — ESI, a local SDE dump, Fuzzwork market aggregates, and zKillboard. Use this whenever a question touches item prices or what something is worth, market orders, type IDs, system security, routes and jump counts, planets and PI schematics, industry indices, or recent kills and gank activity in a system. Reach for it even when the user does not name a data source: "is this route safe", "what does a Catalyst cost", "which planets near me have the right resources", "how many jumps to Amarr" are all this skill. Answering those from memory produces stale numbers, so look them up.
---

# EVE data

Four public sources cover almost every factual question about the game. Pick by what the question needs:

| need | source |
|---|---|
| what something is, where it is, how things connect | local SDE (offline, no rate limit) |
| what something costs right now | Fuzzwork aggregates |
| live game state: orders, indices, structures | ESI |
| who is dying where | zKillboard |

Static facts go to the SDE first. It is a local file, so it costs nothing and cannot rate-limit you, and most "which / where / how many jumps" questions never touch the network.

Everything here is public and needs no API key. Character-private data (skills, wallet, assets, colonies) requires an authenticated ESI session and is out of scope; if the surrounding project already has a cache or token store for that, use it rather than starting a second auth flow.

## Setup

Three environment variables, all optional. Read them rather than hardcoding, so the skill travels between machines:

| variable | meaning | default if unset |
|---|---|---|
| `EVE_SDE_DB` | path to the SDE SQLite file | `${XDG_DATA_HOME:-$HOME/.local/share}/eve-sde/sde.db` |
| `EVE_ESI_UA` | product token in the User-Agent | `eve-notes/1.0` |
| `EVE_ESI_CONTACT` | contact address appended in parentheses | omitted |

```bash
SDE="${EVE_SDE_DB:-${XDG_DATA_HOME:-$HOME/.local/share}/eve-sde/sde.db}"
UA="${EVE_ESI_UA:-eve-notes/1.0}${EVE_ESI_CONTACT:+ ($EVE_ESI_CONTACT)}"
CD="2026-08-18"   # ESI compatibility date, see below
```

CCP asks for a User-Agent that identifies the caller, and uses it to reach you when a script
misbehaves. Without `EVE_ESI_CONTACT` the requests still work, but CCP has no way to warn you
before throttling, so mention it once to the user and carry on rather than blocking on it. Never
invent an address: a fake contact is worse than none, because it reads as evasion.

Keep the product token boring and tool-shaped. `eve-notes/1.0` says a small personal tool is
calling. A name advertising an AI agent or a specific harness invites different handling of your
traffic, and tells every operator downstream more about the caller than the request needs to.

## SDE (static data)

Fuzzwork's conversion of CCP's Static Data Export, about 475 MB unpacked. Download it, or refresh it when a patch changes items or the map:

```bash
mkdir -p "$(dirname "$SDE")"
curl -o "$SDE.gz" https://www.fuzzwork.co.uk/dump/latest-sqlite.db.gz
gunzip -f "$SDE.gz"
```

If the file is missing, offer that command rather than falling back to guesswork.

### Tables that carry most answers

| table | holds |
|---|---|
| `invTypes` | every item: `typeID`, `typeName`, `volume`, `packagedVolume`, `groupID` |
| `invGroups` / `invCategories` | what kind of thing a type is |
| `mapSolarSystems` | `solarSystemID`, `solarSystemName`, `security`, `regionID` |
| `mapSolarSystemJumps` | the stargate graph, one row per connection |
| `mapDenormalize` | celestials: planets, moons, belts, with `solarSystemID` and `typeID` |
| `planetSchematics` | PI recipes, with `cycleTime` in seconds |
| `planetSchematicsTypeMap` | recipe lines: `isInput` 1 for inputs, 0 for the output |
| `planetResources` | per-celestial reagent data |
| `staStations` | NPC stations |
| `industryActivityMaterials` | manufacturing inputs per blueprint |

Schemas drift between dumps. Run `pragma table_info(<table>)` before trusting a column name from memory.

### Worked queries

A PI recipe, inputs and output together. `isInput` separates them:

```sql
select s.schematicName, s.cycleTime, t.typeName, m.quantity, m.isInput
from planetSchematics s
join planetSchematicsTypeMap m on m.schematicID = s.schematicID
join invTypes t on t.typeID = m.typeID
where s.schematicName = 'Coolant';
-- Coolant|3600|Electrolytes|40|1
-- Coolant|3600|Water|40|1
-- Coolant|3600|Coolant|5|0
```

Systems within N jumps, walking the stargate graph. The join tests both ends because `mapSolarSystemJumps` stores each connection once, undirected:

```sql
with recursive r(sys, d) as (
  select 30000142, 0                      -- origin system ID
  union
  select case when j.fromSolarSystemID = r.sys then j.toSolarSystemID else j.fromSolarSystemID end,
         r.d + 1
  from mapSolarSystemJumps j
  join r on j.fromSolarSystemID = r.sys or j.toSolarSystemID = r.sys
  where r.d < 3)
select s.solarSystemName, s.security, min(r.d) as jumps
from r join mapSolarSystems s on s.solarSystemID = r.sys
where s.security >= 0.5
group by r.sys order by jumps;
```

Trade hubs: Jita 30000142, Amarr 30002187, Dodixie 30002659, Rens 30002510, Hek 30002053. The Forge region is 10000002.

## ESI (live game state)

Base `https://esi.evetech.net`. Two headers on every request:

- **User-Agent**, built in the setup section above as `$UA`.
- **`X-Compatibility-Date`.** ESI versions by date instead of by route. The list is at `/meta/compatibility-dates/`; `2026-08-18` was newest as of that date. Pin a date rather than tracking the newest, so a schema change never silently alters an answer.

```bash
curl -sS -H "X-Compatibility-Date: $CD" -A "$UA" "https://esi.evetech.net/universe/systems/" | jq length
```

### The migration gotcha

ESI is mid-migration and the two path styles do not overlap cleanly. Most endpoints answer at the bare path, but some answer **only** under the legacy `/latest/` or `/v1/` prefix, even though the spec lists them at the bare path:

```
/route/30000142/30002187         -> {"error":"Page not found"}
/latest/route/30000142/30002187/ -> [30000142,30000138,...,30002187]
```

When a bare path returns `{"error":"Page not found"}` but the spec says it exists, retry under `/latest/` with a trailing slash before concluding the endpoint is gone. The full spec is at `/meta/openapi.json`; grep `.paths | keys[]` for what exists.

### Public endpoints worth knowing

| path | gives |
|---|---|
| `/status/` | server up, player count, current build |
| `/universe/systems/{id}/` | name, security, constellation |
| `/universe/types/{id}/` | name, volume, group |
| `/markets/{region_id}/orders?type_id=&order_type=sell` | live order book, paginated |
| `/markets/{region_id}/history?type_id=` | daily volume and price history |
| `/markets/prices` | adjusted and average price, all types at once |
| `/industry/systems` | cost indices per system |
| `/latest/route/{origin}/{destination}/?flag=secure` | jump list; `flag` is `secure`, `shortest` or `insecure` |

`order_type` is required on the orders endpoint. An empty `[]` is a real answer meaning no orders, not an error: PLEX returns empty because it does not trade on the regional market, while Tritanium in The Forge returns a full book.

## Fuzzwork market aggregates

For "what does X cost", this beats ESI: one request returns min sell and max buy already aggregated, no pagination, no auth.

```bash
curl -sS "https://market.fuzzwork.co.uk/aggregates/?region=10000002&types=34,35,36" | jq
```

`region=10000002` is The Forge, which is what people mean by Jita price. Pass several type IDs comma-separated. Look the IDs up in `invTypes` first.

## zKillboard

Recent kills per system. This is the honest answer to "is this route safe", because it shows what actually died rather than what should theoretically be safe.

```bash
curl -sS -A "$UA" "https://zkillboard.com/api/kills/systemID/30000142/" | jq -c '.[0:5][] | {killmail_id, value: .zkb.totalValue}'
```

Be gentle with it: it is one person's server, so cache what you fetch and do not loop over a whole route system by system without need.

## Answering with this data

Quote the number and say when you got it. Prices move, so "Tritanium 3.75 ISK, Jita sell, 2026-09-18" stays useful next week in a way that "about 4 ISK" does not.

Cross-check mechanics against the EVE University wiki. These sources say what the game currently contains, not what the rules mean. A price or a jump count is a fact; "alphas cannot do this" is a rule, and rules come from the wiki.

When a query returns nothing, check whether that is the answer before assuming the call failed. Empty market orders, a system with no recent kills, and a PI schematic with no inputs are all real states.
