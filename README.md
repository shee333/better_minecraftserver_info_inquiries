# C418 Minecraft Query

Repository: https://github.com/shee333/better_minecraftserver_info_inquiries

AstrBot plugin for querying Minecraft CMI player data from a SQLite database and checking Minecraft Java server status.

## Features

- Query player public profile, balance, total playtime, last login and last logoff.
- Query Home count only. Home names, worlds and coordinates are never returned to normal members.
- Query playtime ranking, balance ranking and recent login players.
- Query banned player list and ban details, including ban time, operator and reason.
- Query Minecraft Java server online status, latency, version, MOTD and player count for multiple named servers.
- Render Minecraft server status as a local PNG image, with merged-forward text fallback.
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

## Server Status

The server status query uses the Minecraft Java status ping protocol directly and does not require extra Python dependencies.

Default server status targets:

- 轮换服: `turbo1.yunmc.vip:30175`
- C418: `mc39.rhymc.com:24465`
- 群组服: `mc39.rhymc.com:24463`

Configurable fields:

- `server_status_servers`: JSON server list. Each item supports `name`, `host`, `port` and `aliases`.
- `server_status_name`: old single-server display name, kept for compatibility.
- `server_status_host`: old single-server domain or IP, kept for compatibility.
- `server_status_port`: old single-server port, kept for compatibility.
- `server_status_timeout_seconds`: connection timeout, default `3.0`
- `server_status_show_sample_players`: whether to show player names returned by the server status protocol
- `server_status_render_image`: whether to render status results as a local PNG image, default `true`

## Commands

These commands are mainly for fallback and debugging. Natural-language usage is also supported through LLM tools.

- `查询玩家 <玩家名>`
- `游玩排行 [数量]`
- `余额排行 [数量]`
- `最近上线 [数量]`
- `查询home数量 <玩家名>`
- `封禁列表`
- `封禁状态 <玩家名>`
- `服务器状态 [轮换服|C418|群组服]`
- `MC状态 [轮换服|C418|群组服]`

## LLM Tools

- `shee33_mc_query_player`
- `shee33_mc_query_home_count`
- `shee33_mc_rank_playtime`
- `shee33_mc_rank_balance`
- `shee33_mc_recent_players`
- `shee33_mc_list_banned_players`
- `shee33_mc_query_ban_status`
- `shee33_mc_server_status`

## Natural Language Examples

- `@机器人 查一下 shee33 的服务器信息`
- `@机器人 shee33 玩了多久？`
- `@机器人 余额最高的是谁？`
- `@机器人 最近谁上线了？`
- `@机器人 BigSoap 有几个家？`
- `@机器人 目前有哪些玩家被封禁了？`
- `@机器人 ceester 为什么被封？`
- `@机器人 服务器现在开着吗？`
- `@机器人 查一下 MC 在线人数`
- `@机器人 C418 现在在线吗？`
- `@机器人 轮换服延迟多少？`
- `@机器人 群组服有几个人在线？`

## Privacy Rules

Normal members can query:

- player name and display name
- balance
- total playtime
- last login and last logoff
- Home count only
- ban status, ban time, operator and reason
- rankings and recent login list
- Minecraft server online status, latency, version, MOTD and online player count

The plugin does not read or return:

- `Ips`
- `LockedIps`
- Home names
- Home worlds or coordinates
- logout/death/teleport locations
- internal notes or other security-sensitive fields
