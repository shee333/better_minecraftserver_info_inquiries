# C418 Minecraft Query

Repository: https://github.com/shee333/better_minecraftserver_info_inquiries

AstrBot plugin for querying Minecraft CMI player data from a SQLite database.

## Features

- Query player public profile, balance, total playtime, last login and last logoff.
- Query Home count only. Home names, worlds and coordinates are never returned to normal members.
- Query playtime ranking, balance ranking and recent login players.
- Query banned player list and ban details, including ban time, operator and reason.
- Never reads or returns IP-related fields such as `Ips` or `LockedIps`.
- Sends query results through QQ merged forward messages to avoid flooding group chat.
- Reacts to accepted query messages with QQ emoji feedback through NapCat `set_msg_emoji_like`.
- Provides natural-language LLM tools whose names start with `shee33_mc_`.

## Data Source

Default server database path:

```text
E:\C418\plugins\CMI\cmi.sqlite.db
```

For compatibility with older configuration values, if `cmi.sqlite` does not exist, the plugin also tries `cmi.sqlite.db`. For local development, if the server path does not exist, the plugin falls back to:

```text
cmi.sqlite.db
```

The database is opened in read-only mode.

## Commands

These commands are mainly for fallback and debugging. Natural-language usage is also supported through LLM tools.

- `查询玩家 <玩家名>`
- `游玩排行 [数量]`
- `余额排行 [数量]`
- `最近上线 [数量]`
- `查询home数量 <玩家名>`
- `封禁列表`
- `封禁状态 <玩家名>`

## LLM Tools

- `shee33_mc_query_player`
- `shee33_mc_query_home_count`
- `shee33_mc_rank_playtime`
- `shee33_mc_rank_balance`
- `shee33_mc_recent_players`
- `shee33_mc_list_banned_players`
- `shee33_mc_query_ban_status`

## Natural Language Examples

- `@机器人 查一下 shee33 的服务器信息`
- `@机器人 shee33 玩了多久？`
- `@机器人 余额最高的是谁？`
- `@机器人 最近谁上线了？`
- `@机器人 BigSoap 有几个家？`
- `@机器人 目前有哪些玩家被封禁了？`
- `@机器人 ceester 为什么被封？`

## Privacy Rules

Normal members can query:

- player name and display name
- balance
- total playtime
- last login and last logoff
- Home count only
- ban status, ban time, operator and reason
- rankings and recent login list

The plugin does not read or return:

- `Ips`
- `LockedIps`
- Home names
- Home worlds or coordinates
- logout/death/teleport locations
- internal notes or other security-sensitive fields
