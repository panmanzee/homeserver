"""
Daily practice bot for a small Discord server.

Commands
  /link <leetcode username>                    link + verify your LeetCode account
  /unlink                                      remove the link
  /import                                      pull your existing LeetCode progress
  /solve <number> [difficulty] [proof image]   report a solved problem (auto-verified via LeetCode)
  /profile [member]                             problems solved per category, streak, proofs
  /leaderboard [period]                         today / this week / all time
  /undo                                         delete your latest report
  /help                                         list all commands

Every day at POST_TIME (Asia/Bangkok) the bot posts today's board to the
leaderboard channel.

Environment variables:
  DISCORD_TOKEN          bot token from the Developer Portal
  LEADERBOARD_CHANNEL_ID channel where the daily board is posted
  PROOF_CHANNEL_ID       channel where proof images are archived
  GUILD_ID               (optional) your server id, makes slash commands appear instantly
  DB_PATH                (optional) sqlite file path, default points.db
"""

import os
import secrets
import sqlite3
import datetime as dt
from zoneinfo import ZoneInfo

import aiohttp
import discord
from discord import app_commands
from discord.ext import tasks

TZ = ZoneInfo("Asia/Bangkok")
POST_TIME = dt.time(23, 59, tzinfo=TZ)

# Points used only for ordering the board. Change to whatever feels fair.
WEIGHTS = {"easy": 1, "medium": 3, "hard": 5}

TOKEN = os.environ["DISCORD_TOKEN"]
LEADERBOARD_CHANNEL_ID = int(os.environ["LEADERBOARD_CHANNEL_ID"])
PROOF_CHANNEL_ID = int(os.environ["PROOF_CHANNEL_ID"])
GUILD_ID = int(os.environ["GUILD_ID"]) if os.environ.get("GUILD_ID") else None
DB_PATH = os.environ.get("DB_PATH", "points.db")

# ---------- database ----------
db = sqlite3.connect(DB_PATH)
db.execute(
    """
    CREATE TABLE IF NOT EXISTS submissions (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER NOT NULL,
        difficulty TEXT    NOT NULL,
        problem    INTEGER NOT NULL,
        day        TEXT    NOT NULL,
        proof_url  TEXT    NOT NULL DEFAULT '',
        created_at TEXT    NOT NULL,
        verified   INTEGER NOT NULL DEFAULT 0
    )
    """
)
if "verified" not in {r[1] for r in db.execute("PRAGMA table_info(submissions)")}:
    db.execute("ALTER TABLE submissions ADD COLUMN verified INTEGER NOT NULL DEFAULT 0")
db.execute(
    """
    CREATE TABLE IF NOT EXISTS lc_users (
        user_id     INTEGER PRIMARY KEY,
        lc_username TEXT    NOT NULL,
        code        TEXT    NOT NULL,
        verified    INTEGER NOT NULL DEFAULT 0
    )
    """
)
db.execute(
    """
    CREATE TABLE IF NOT EXISTS lc_legacy (
        user_id INTEGER PRIMARY KEY,
        easy    INTEGER NOT NULL DEFAULT 0,
        medium  INTEGER NOT NULL DEFAULT 0,
        hard    INTEGER NOT NULL DEFAULT 0
    )
    """
)
db.execute(
    """
    CREATE TABLE IF NOT EXISTS lc_problems (
        slug       TEXT PRIMARY KEY,
        number     INTEGER NOT NULL,
        difficulty TEXT    NOT NULL,
        title      TEXT    NOT NULL
    )
    """
)
# one problem number can only be counted once per player
db.execute("CREATE UNIQUE INDEX IF NOT EXISTS uniq_user_problem ON submissions (user_id, problem)")
db.commit()


def today() -> dt.date:
    return dt.datetime.now(TZ).date()


def score(counts: dict) -> int:
    return sum(WEIGHTS[k] * counts[k] for k in WEIGHTS)


def fmt_counts(c: dict) -> str:
    return f"easy:{c['easy']}  medium:{c['medium']}  hard:{c['hard']}"


def get_board(since: dt.date | None):
    q = "SELECT user_id, difficulty, COUNT(*) FROM submissions"
    params = []
    if since:
        q += " WHERE day >= ?"
        params.append(since.isoformat())
    q += " GROUP BY user_id, difficulty"
    data: dict[int, dict] = {}
    for uid, diff, n in db.execute(q, params):
        data.setdefault(uid, {"easy": 0, "medium": 0, "hard": 0})[diff] = n
    if since is None:  # earlier progress imported from LeetCode only counts for the all-time board
        for uid, e, m, h in db.execute("SELECT user_id, easy, medium, hard FROM lc_legacy"):
            d = data.setdefault(uid, {"easy": 0, "medium": 0, "hard": 0})
            d["easy"] += e; d["medium"] += m; d["hard"] += h
    return sorted(data.items(), key=lambda kv: score(kv[1]), reverse=True)


def board_embed(title: str, since: dt.date | None, show_today: bool = False) -> discord.Embed:
    rows = get_board(since)
    today_counts = dict(get_board(today())) if show_today else {}
    if not rows:
        desc = "No reports yet."
    else:
        lines = []
        for i, (uid, c) in enumerate(rows[:25], 1):
            line = f"**{i}.** <@{uid}>  {fmt_counts(c)}  (score {score(c)})"
            t = today_counts.get(uid)
            if t:
                line += f"  | today +{sum(t.values())}"
            lines.append(line)
        desc = "\n".join(lines)
    emb = discord.Embed(title=title, description=desc, color=0x5865F2)
    emb.set_footer(text="score = easy x{easy} + medium x{medium} + hard x{hard}".format(**WEIGHTS))
    return emb


def solved_by_difficulty(uid: int) -> dict[str, list[int]]:
    out = {"easy": [], "medium": [], "hard": []}
    for diff, prob in db.execute(
        "SELECT difficulty, problem FROM submissions WHERE user_id = ? ORDER BY problem", (uid,)
    ):
        out[diff].append(prob)
    return out


def fmt_problem_list(nums: list[int], limit: int = 1000) -> str:
    if not nums:
        return "none yet"
    text = ", ".join(f"#{n}" for n in nums)
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(", ", 1)[0]
    return f"{cut}, ... (+{len(nums) - cut.count('#')} more)"


def get_streak(uid: int) -> int:
    days = {r[0] for r in db.execute("SELECT DISTINCT day FROM submissions WHERE user_id = ?", (uid,))}
    d = today()
    if d.isoformat() not in days:  # allow the streak to stay alive until the day ends
        d -= dt.timedelta(days=1)
    n = 0
    while d.isoformat() in days:
        n += 1
        d -= dt.timedelta(days=1)
    return n


# ---------- LeetCode (unofficial public GraphQL, no login needed) ----------
LC_URL = "https://leetcode.com/graphql"
LC_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Referer": "https://leetcode.com",
}


class LeetCodeError(Exception):
    pass


async def lc_query(query: str, variables: dict) -> dict:
    try:
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(LC_URL, json={"query": query, "variables": variables}, headers=LC_HEADERS) as r:
                if r.status != 200:
                    raise LeetCodeError(f"LeetCode answered HTTP {r.status}")
                return await r.json()
    except (aiohttp.ClientError, TimeoutError) as exc:
        raise LeetCodeError(f"could not reach LeetCode ({exc.__class__.__name__})") from exc


async def lc_bio(username: str) -> str | None:
    """Profile 'about me' text, or None if the user does not exist."""
    data = await lc_query(
        "query($u:String!){matchedUser(username:$u){username profile{aboutMe}}}", {"u": username}
    )
    user = (data.get("data") or {}).get("matchedUser")
    if not user:
        return None
    return (user.get("profile") or {}).get("aboutMe") or ""


async def lc_recent_ac(username: str) -> list[dict]:
    data = await lc_query(
        "query($u:String!,$n:Int){recentAcSubmissionList(username:$u,limit:$n){title titleSlug timestamp}}",
        {"u": username, "n": 20},
    )
    return (data.get("data") or {}).get("recentAcSubmissionList") or []


async def lc_problem(slug: str, title: str) -> tuple[int, str] | None:
    """(number, difficulty) for a problem slug; cached because it never changes."""
    row = db.execute("SELECT number, difficulty FROM lc_problems WHERE slug = ?", (slug,)).fetchone()
    if row:
        return row[0], row[1]
    data = await lc_query(
        "query($s:String!){question(titleSlug:$s){questionFrontendId difficulty}}", {"s": slug}
    )
    q = (data.get("data") or {}).get("question")
    if not q:
        return None
    number, diff = int(q["questionFrontendId"]), q["difficulty"].lower()
    db.execute("INSERT OR REPLACE INTO lc_problems VALUES (?,?,?,?)", (slug, number, diff, title))
    db.commit()
    return number, diff


async def lc_totals(username: str) -> dict[str, int]:
    """Public per-difficulty count of distinct accepted problems."""
    data = await lc_query(
        "query($u:String!){userProfileUserQuestionProgressV2(userSlug:$u){numAcceptedQuestions{count difficulty}}}",
        {"u": username},
    )
    rows = ((data.get("data") or {}).get("userProfileUserQuestionProgressV2") or {}).get("numAcceptedQuestions")
    if rows is None:
        raise LeetCodeError("could not read your solved counts (is your profile public?)")
    return {r["difficulty"].lower(): int(r["count"]) for r in rows}


def recorded_counts(uid: int) -> dict[str, int]:
    out = {"easy": 0, "medium": 0, "hard": 0}
    for diff, n in db.execute("SELECT difficulty, COUNT(*) FROM submissions WHERE user_id = ? GROUP BY difficulty", (uid,)):
        out[diff] = n
    return out


def get_legacy(uid: int) -> dict[str, int]:
    row = db.execute("SELECT easy, medium, hard FROM lc_legacy WHERE user_id = ?", (uid,)).fetchone()
    return dict(zip(("easy", "medium", "hard"), row)) if row else {"easy": 0, "medium": 0, "hard": 0}


async def sync_legacy(uid: int, username: str) -> dict[str, int]:
    """Make the bot's count for this member equal LeetCode's own total.
    legacy = LeetCode total - problems already recorded individually."""
    totals = await lc_totals(username)
    rec = recorded_counts(uid)
    legacy = {k: max(0, totals.get(k, 0) - rec[k]) for k in ("easy", "medium", "hard")}
    db.execute(
        "INSERT OR REPLACE INTO lc_legacy (user_id, easy, medium, hard) VALUES (?,?,?,?)",
        (uid, legacy["easy"], legacy["medium"], legacy["hard"]),
    )
    db.commit()
    return legacy


async def import_progress(uid: int, username: str) -> tuple[int, dict[str, int]]:
    """Record recent accepted problems individually, then fill the rest as a count."""
    added = 0
    seen: set[int] = set()
    for sub in await lc_recent_ac(username):
        info = await lc_problem(sub["titleSlug"], sub["title"])
        if not info or info[0] in seen:
            continue
        seen.add(info[0])
        day = dt.datetime.fromtimestamp(int(sub["timestamp"]), TZ).date().isoformat()
        cur = db.execute(
            "INSERT OR IGNORE INTO submissions (user_id, difficulty, problem, day, proof_url, created_at, verified) "
            "VALUES (?,?,?,?,?,?,1)",
            (uid, info[1], info[0], day, "", dt.datetime.now(TZ).isoformat()),
        )
        added += cur.rowcount
    db.commit()
    return added, await sync_legacy(uid, username)


# ---------- bot ----------
class Bot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self):
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()
        daily_board.start()


bot = Bot()


@bot.tree.command(name="link", description="Link and verify your LeetCode account")
@app_commands.describe(username="Your LeetCode username (the one in your profile URL)")
async def link(interaction: discord.Interaction, username: str):
    username = username.strip()
    await interaction.response.defer(ephemeral=True)

    taken = db.execute(
        "SELECT user_id FROM lc_users WHERE lower(lc_username) = lower(?) AND verified = 1 AND user_id != ?",
        (username, interaction.user.id),
    ).fetchone()
    if taken:
        await interaction.followup.send("That LeetCode account is already linked to another member.", ephemeral=True)
        return

    try:
        bio = await lc_bio(username)
    except LeetCodeError as exc:
        await interaction.followup.send(f"LeetCode check failed: {exc}. Try again in a minute.", ephemeral=True)
        return
    if bio is None:
        await interaction.followup.send(f"LeetCode user `{username}` does not exist.", ephemeral=True)
        return

    row = db.execute("SELECT lc_username, code FROM lc_users WHERE user_id = ?", (interaction.user.id,)).fetchone()
    if row and row[0].lower() == username.lower():
        code = row[1]
    else:
        code = "practice-" + secrets.token_hex(3)
        db.execute(
            "INSERT OR REPLACE INTO lc_users (user_id, lc_username, code, verified) VALUES (?,?,?,0)",
            (interaction.user.id, username, code),
        )
        db.commit()

    if code in bio:
        db.execute("UPDATE lc_users SET verified = 1 WHERE user_id = ?", (interaction.user.id,))
        db.commit()
        try:
            added, legacy = await import_progress(interaction.user.id, username)
            extra = (f"\nImported your LeetCode progress: {added} recent problem(s) with numbers + "
                     f"{sum(legacy.values())} earlier solve(s) as a count.")
        except LeetCodeError as exc:
            extra = f"\nCould not import your progress yet ({exc}). Run /import later."
        await interaction.followup.send(
            f"Linked and verified: `{username}`. You can remove the code from your bio now. "
            f"Use `/solve <number>` after you solve a problem.{extra}",
            ephemeral=True,
        )
    else:
        await interaction.followup.send(
            f"To prove `{username}` is yours: put this code anywhere in your LeetCode profile "
            f"**About me / Summary** (Edit Profile), save it, then run `/link {username}` again.\n"
            f"Code: `{code}`",
            ephemeral=True,
        )


@bot.tree.command(name="import", description="Pull your existing LeetCode progress into the bot")
async def import_cmd(interaction: discord.Interaction):
    acct = db.execute("SELECT lc_username FROM lc_users WHERE user_id = ? AND verified = 1", (interaction.user.id,)).fetchone()
    if not acct:
        await interaction.response.send_message("Link your account first with `/link <username>`.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True)
    try:
        added, legacy = await import_progress(interaction.user.id, acct[0])
    except LeetCodeError as exc:
        await interaction.followup.send(f"LeetCode check failed: {exc}. Try again in a minute.", ephemeral=True)
        return
    total = {k: recorded_counts(interaction.user.id)[k] + legacy[k] for k in legacy}
    await interaction.followup.send(
        f"Synced with LeetCode: {added} new recent problem(s) added. Your total is now {fmt_counts(total)}.\n"
        "Only your latest ~20 solves keep problem numbers; older ones are counted without numbers "
        "(LeetCode only shows the full list to the logged-in owner).",
        ephemeral=True,
    )


@bot.tree.command(name="unlink", description="Remove your linked LeetCode account")
async def unlink(interaction: discord.Interaction):
    db.execute("DELETE FROM lc_users WHERE user_id = ?", (interaction.user.id,))
    db.commit()
    await interaction.response.send_message("Unlinked. Your past solves stay on the board.", ephemeral=True)


@bot.tree.command(name="solve", description="Report a solved problem (auto-verified through your linked LeetCode)")
@app_commands.describe(
    number="Problem number (e.g. 1 for Two Sum)",
    difficulty="Only needed with a proof image, when you have no linked account",
    proof="Screenshot of the accepted solution (fallback if you have no linked account)",
)
@app_commands.choices(
    difficulty=[
        app_commands.Choice(name="Easy", value="easy"),
        app_commands.Choice(name="Medium", value="medium"),
        app_commands.Choice(name="Hard", value="hard"),
    ]
)
async def solve(
    interaction: discord.Interaction,
    number: app_commands.Range[int, 1, 9999],
    difficulty: app_commands.Choice[str] | None = None,
    proof: discord.Attachment | None = None,
):
    uid = interaction.user.id
    dup = db.execute("SELECT day FROM submissions WHERE user_id = ? AND problem = ?", (uid, number)).fetchone()
    if dup:
        await interaction.response.send_message(
            f"You already reported problem #{number} on {dup[0]}. Use /undo if that was a mistake.",
            ephemeral=True,
        )
        return

    await interaction.response.defer()
    acct = db.execute("SELECT lc_username FROM lc_users WHERE user_id = ? AND verified = 1", (uid,)).fetchone()
    verified, proof_url, diff_value, day = 0, "", None, today().isoformat()

    if acct:
        # ---- automatic verification through LeetCode ----
        try:
            found = None
            for sub in await lc_recent_ac(acct[0]):
                info = await lc_problem(sub["titleSlug"], sub["title"])
                if info and info[0] == number:
                    found = (info[1], int(sub["timestamp"]))
                    break
        except LeetCodeError as exc:
            await interaction.followup.send(f"LeetCode check failed: {exc}. Try again in a minute.", ephemeral=True)
            return
        if not found:
            await interaction.followup.send(
                f"I could not find an accepted submission for #{number} on `{acct[0]}` among your latest 20. "
                "Make sure it is Accepted, your profile/submissions are public, and run /solve soon after solving.",
                ephemeral=True,
            )
            return
        diff_value = found[0]
        day = dt.datetime.fromtimestamp(found[1], TZ).date().isoformat()
        verified = 1
    else:
        # ---- manual fallback: screenshot proof ----
        if difficulty is None or proof is None:
            await interaction.followup.send(
                "Link your LeetCode account with `/link <username>` for automatic verification, "
                "or give both `difficulty` and a `proof` screenshot.",
                ephemeral=True,
            )
            return
        if not (proof.content_type or "").startswith("image/"):
            await interaction.followup.send("Please attach an image as proof.", ephemeral=True)
            return
        diff_value = difficulty.value
        try:
            channel = bot.get_channel(PROOF_CHANNEL_ID) or await bot.fetch_channel(PROOF_CHANNEL_ID)
            msg = await channel.send(  # attachment links expire, so re-upload and keep this link
                content=f"<@{uid}> | #{number} ({diff_value}) | {day}",
                file=await proof.to_file(),
                allowed_mentions=discord.AllowedMentions.none(),
                silent=True,
            )
            proof_url = msg.jump_url
        except discord.HTTPException:
            await interaction.followup.send(
                "Could not save your proof image (bot permission problem?). Nothing was recorded.", ephemeral=True
            )
            return

    db.execute(
        "INSERT INTO submissions (user_id, difficulty, problem, day, proof_url, created_at, verified) "
        "VALUES (?,?,?,?,?,?,?)",
        (uid, diff_value, number, day, proof_url, dt.datetime.now(TZ).isoformat(), verified),
    )
    db.commit()

    if verified:
        try:
            await sync_legacy(uid, acct[0])
        except LeetCodeError:
            pass  # not critical, /import can fix it later
    mine = next((c for u, c in get_board(None) if u == uid), {"easy": 0, "medium": 0, "hard": 0})
    tag = "verified on LeetCode" if verified else "manual proof"
    await interaction.followup.send(
        f"Recorded #{number} ({diff_value.capitalize()}, {tag}, solved {day}) for {interaction.user.mention}. "
        f"Total: {fmt_counts(mine)}  | streak: {get_streak(uid)} day(s)",
        allowed_mentions=discord.AllowedMentions.none(),
        silent=True,
    )


@bot.tree.command(name="profile", description="See the problems someone has solved")
@app_commands.describe(member="Whose profile to view (default: you)")
async def profile(interaction: discord.Interaction, member: discord.Member | None = None):
    member = member or interaction.user
    uid = member.id
    solved = solved_by_difficulty(uid)
    legacy = get_legacy(uid)
    totals = {k: len(v) + legacy[k] for k, v in solved.items()}

    emb = discord.Embed(title=f"{member.display_name}'s profile", color=0x57F287)
    emb.description = (
        f"**Total solved: {sum(totals.values())}**  (score {score(totals)})\n"
        f"Easy: {totals['easy']}  |  Medium: {totals['medium']}  |  Hard: {totals['hard']}\n"
        f"Streak: {get_streak(uid)} day(s)"
    )
    acct = db.execute("SELECT lc_username FROM lc_users WHERE user_id = ? AND verified = 1", (uid,)).fetchone()
    emb.description += f"\nLeetCode: {acct[0]}" if acct else "\nLeetCode: not linked (/link)"
    for diff in ("easy", "medium", "hard"):
        emb.add_field(
            name=f"{diff.capitalize()} ({totals[diff]})",
            value=fmt_problem_list(solved[diff]) + (f"  (+{legacy[diff]} earlier, no numbers)" if legacy[diff] else ""),
            inline=False,
        )

    recent = db.execute(
        "SELECT day, difficulty, problem, proof_url, verified FROM submissions WHERE user_id = ? ORDER BY id DESC LIMIT 5",
        (uid,),
    ).fetchall()
    if recent:
        lines = [
            f"{day} | #{prob} ({diff}) | " + ("verified" if ver else f"[proof]({url})")
            for day, diff, prob, url, ver in recent
        ]
        emb.add_field(name="Latest solves", value="\n".join(lines), inline=False)
    emb.set_thumbnail(url=member.display_avatar.url)
    await interaction.response.send_message(embed=emb)


@bot.tree.command(name="help", description="Show all commands")
async def help_cmd(interaction: discord.Interaction):
    emb = discord.Embed(title="Practice bot - commands", color=0xFEE75C)
    emb.add_field(
        name="/link <leetcode username>",
        value="Link your LeetCode account once. The bot gives you a code to paste into your LeetCode "
              "profile About/Summary to prove it is yours, then run /link again.",
        inline=False,
    )
    emb.add_field(
        name="/solve <number>",
        value="Report a solved problem by number. The bot checks your latest accepted LeetCode submissions "
              "and fills in the difficulty automatically. Each problem counts once per person. "
              "No linked account? Add `difficulty` and a `proof` screenshot instead.",
        inline=False,
    )
    emb.add_field(
        name="/import",
        value="Sync your existing LeetCode progress (also runs automatically when you /link).",
        inline=False,
    )
    emb.add_field(name="/unlink", value="Remove your linked LeetCode account.", inline=False)
    emb.add_field(
        name="/profile [member]",
        value="Problems solved per category (with numbers), score, streak and latest solves.",
        inline=False,
    )
    emb.add_field(
        name="/leaderboard [period]",
        value="Ranking for today, this week or all time.",
        inline=False,
    )
    emb.add_field(name="/undo", value="Delete your latest report if you made a mistake.", inline=False)
    emb.set_footer(text="Score: easy x{easy}, medium x{medium}, hard x{hard}. The overall board posts daily at 23:59 (Bangkok).".format(**WEIGHTS))
    await interaction.response.send_message(embed=emb, ephemeral=True)


@bot.tree.command(name="leaderboard", description="Show the leaderboard")
@app_commands.choices(
    period=[
        app_commands.Choice(name="Today", value="today"),
        app_commands.Choice(name="This week", value="week"),
        app_commands.Choice(name="All time", value="all"),
    ]
)
async def leaderboard(interaction: discord.Interaction, period: app_commands.Choice[str] | None = None):
    p = period.value if period else "today"
    if p == "today":
        emb = board_embed(f"Leaderboard - {today().isoformat()}", today())
    elif p == "week":
        emb = board_embed("Leaderboard - this week", today() - dt.timedelta(days=today().weekday()))
    else:
        emb = board_embed("Leaderboard - all time", None)
    await interaction.response.send_message(embed=emb)


@bot.tree.command(name="undo", description="Delete your latest report (for mistakes)")
async def undo(interaction: discord.Interaction):
    row = db.execute(
        "SELECT id, difficulty, day, problem FROM submissions WHERE user_id = ? ORDER BY id DESC LIMIT 1",
        (interaction.user.id,),
    ).fetchone()
    if not row:
        await interaction.response.send_message("Nothing to undo.", ephemeral=True)
        return
    db.execute("DELETE FROM submissions WHERE id = ?", (row[0],))
    db.commit()
    await interaction.response.send_message(f"Removed your latest report (#{row[3]}, {row[1]}, {row[2]}).", ephemeral=True)


@tasks.loop(time=POST_TIME)
async def daily_board():
    channel = bot.get_channel(LEADERBOARD_CHANNEL_ID) or await bot.fetch_channel(LEADERBOARD_CHANNEL_ID)
    await channel.send(embed=board_embed(f"Overall board - {today().isoformat()}", None, show_today=True), silent=True)


@daily_board.before_loop
async def before_daily():
    await bot.wait_until_ready()


if __name__ == "__main__":
    bot.run(TOKEN)
