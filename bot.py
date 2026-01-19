import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time as dtime, timedelta
import pytz
import os
import json
import asyncio

# ================== ENV ==================
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("❌ Thiếu TOKEN")

tz = pytz.timezone("Asia/Ho_Chi_Minh")
DATA_FILE = "attendance.json"

# ================== LOAD / SAVE ==================
def load():
    if not os.path.exists(DATA_FILE):
        return {
            "attendance": {},
            "attendance_channel": {},
            "weekly_summary_channel": {},
            "weekly_summary_role": {}
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

data = load()
attendance = data["attendance"]
attendance_channel = data["attendance_channel"]
weekly_summary_channel = data["weekly_summary_channel"]
weekly_summary_role = data["weekly_summary_role"]

# ================== TIME ==================
def now():
    return datetime.now(tz)

def today():
    return now().strftime("%Y-%m-%d")

def in_session():
    t = now().time()
    if dtime(12, 0) <= t <= dtime(16, 0):
        return "noon"
    if dtime(18, 0) <= t <= dtime(22, 0):
        return "evening"
    return None

def week_dates():
    today_dt = now().date()
    start = today_dt - timedelta(days=(today_dt.weekday() + 1) % 7)
    return [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

# ================== BOT ==================
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ================== PERMISSION ==================
def admin_only():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)

# ================== VIEW ==================
class AttendanceView(discord.ui.View):
    def __init__(self, gid):
        super().__init__(timeout=None)
        self.gid = gid

    @discord.ui.button(label="📍 Điểm danh", style=discord.ButtonStyle.success)
    async def attend(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = in_session()
        if not session:
            await interaction.response.send_message("⛔ Ngoài giờ điểm danh", ephemeral=True)
            return

        gid = str(interaction.guild.id)
        uid = str(interaction.user.id)
        day = today()

        attendance.setdefault(gid, {}).setdefault(day, {}).setdefault("noon", [])
        attendance.setdefault(gid, {}).setdefault(day, {}).setdefault("evening", [])

        if any(u["uid"] == uid for u in attendance[gid][day][session]):
            await interaction.response.send_message("⚠️ Bạn đã điểm danh buổi này rồi", ephemeral=True)
            return

        attendance[gid][day][session].append({
            "uid": uid,
            "time": now().strftime("%H:%M")
        })
        save()

        await interaction.response.send_message("✅ Điểm danh thành công", ephemeral=True)
        await interaction.message.edit(
            embed=build_embed(gid, day),
            view=AttendanceView(gid)
        )

# ================== EMBED NGÀY ==================
def build_embed(gid, day):
    noon = attendance.get(gid, {}).get(day, {}).get("noon", [])
    evening = attendance.get(gid, {}).get(day, {}).get("evening", [])

    session = in_session()
    if session == "noon":
        color = discord.Color.from_rgb(255, 183, 77)
    elif session == "evening":
        color = discord.Color.from_rgb(88, 101, 242)
    else:
        color = discord.Color.blurple()

    embed = discord.Embed(
        title="📍 BẢNG ĐIỂM DANH",
        description=(
            f"🗓️ Ngày: `{day}`\n"
            f"🌤️ Trưa: 12:00 – 16:00\n"
            f"🌙 Tối: 18:00 – 22:00"
        ),
        color=color
    )

    embed.add_field(
        name=f"🌤️ BUỔI TRƯA ({len(noon)})",
        value="```" + "\n".join(
            f"{i:02d}. <@{u['uid']}> | {u['time']}"
            for i, u in enumerate(noon, 1)
        ) + "```" if noon else "```Chưa có```",
        inline=False
    )

    embed.add_field(
        name=f"🌙 BUỔI TỐI ({len(evening)})",
        value="```" + "\n".join(
            f"{i:02d}. <@{u['uid']}> | {u['time']}"
            for i, u in enumerate(evening, 1)
        ) + "```" if evening else "```Chưa có```",
        inline=False
    )

    return embed

# ================== EMBED TUẦN ==================
def build_week_attendance_tables(gid, role: discord.Role):
    dates = week_dates()
    user_count = {}

    for day in dates:
        day_data = attendance.get(gid, {}).get(day, {})
        for s in ["noon", "evening"]:
            for u in day_data.get(s, []):
                user_count[u["uid"]] = user_count.get(u["uid"], 0) + 1

    role_members = {str(m.id): m for m in role.members}

    full_list = []
    under_5 = []

    for uid, total in user_count.items():
        if uid in role_members:
            m = role_members[uid]
            full_list.append((m, total))
            if total < 5:
                under_5.append((m, total))

    full_list.sort(key=lambda x: x[1], reverse=True)
    under_5.sort(key=lambda x: x[1])

    embed = discord.Embed(
        title="📊 BẢNG TỔNG ĐIỂM DANH TUẦN",
        description=f"Từ `{dates[0]}` → `{dates[-1]}`\nRole theo dõi: {role.mention}",
        color=discord.Color.orange()
    )

    embed.add_field(
        name="🟦 Tổng điểm danh",
        value="```" + "\n".join(
            f"{m.display_name} | {t} buổi"
            for m, t in full_list
        ) + "```",
        inline=False
    )

    embed.add_field(
        name="🟥 Dưới 5 buổi (cần xử lý)",
        value="```" + "\n".join(
            f"{m.display_name} | {t} buổi"
            for m, t in under_5
        ) + "```" if under_5 else "```Không có```",
        inline=False
    )

    return embed

# ================== COMMAND ==================
@tree.command(name="diemdanh")
@admin_only()
async def diemdanh(interaction: discord.Interaction, channel: discord.TextChannel):
    gid = str(interaction.guild.id)
    attendance_channel[gid] = str(channel.id)
    save()
    await channel.send(embed=build_embed(gid, today()), view=AttendanceView(gid))
    await interaction.response.send_message("✅ Đã tạo bảng điểm danh", ephemeral=True)

@tree.command(name="testevery")
@admin_only()
@app_commands.choices(buoi=[
    app_commands.Choice(name="Trưa", value="noon"),
    app_commands.Choice(name="Tối", value="evening")
])
async def testevery(interaction: discord.Interaction, buoi: app_commands.Choice[str]):
    gid = str(interaction.guild.id)
    channel = bot.get_channel(int(attendance_channel.get(gid)))
    if not channel:
        await interaction.response.send_message("❌ Chưa set kênh điểm danh", ephemeral=True)
        return

    text = "@everyone 🌤️ **[TEST] MỞ ĐIỂM DANH TRƯA**" if buoi.value == "noon" \
        else "@everyone 🌙 **[TEST] MỞ ĐIỂM DANH TỐI**"

    msg = await channel.send(text)
    await interaction.response.send_message("✅ Đã gửi test", ephemeral=True)
    await asyncio.sleep(60)
    await msg.delete()

@tree.command(name="settongtuan")
@admin_only()
async def settongtuan(interaction: discord.Interaction, channel: discord.TextChannel, role: discord.Role):
    gid = str(interaction.guild.id)
    weekly_summary_channel[gid] = str(channel.id)
    weekly_summary_role[gid] = str(role.id)
    save()
    await interaction.response.send_message("✅ Đã set auto tổng tuần (23:59 Thứ 7)", ephemeral=True)

# ================== AUTO EVERYONE ==================
@tasks.loop(seconds=30)
async def notify_session():
    t = now().strftime("%H:%M")
    for gid, cid in attendance_channel.items():
        ch = bot.get_channel(int(cid))
        if not ch:
            continue
        if t == "12:00":
            m = await ch.send("@everyone 🌤️ **MỞ BẢNG ĐIỂM DANH TRƯA**")
            await asyncio.sleep(60)
            await m.delete()
        if t == "18:00":
            m = await ch.send("@everyone 🌙 **MỞ BẢNG ĐIỂM DANH TỐI**")
            await asyncio.sleep(60)
            await m.delete()

# ================== AUTO WEEK ==================
@tasks.loop(minutes=1)
async def auto_week():
    n = now()
    if n.weekday() != 5 or n.strftime("%H:%M") != "23:59":
        return

    for gid, ch_id in weekly_summary_channel.items():
        ch = bot.get_channel(int(ch_id))
        if not ch:
            continue
        role = ch.guild.get_role(int(weekly_summary_role[gid]))
        if role:
            await ch.send(embed=build_week_attendance_tables(gid, role))

# ================== READY ==================
@bot.event
async def on_ready():
    await tree.sync()
    notify_session.start()
    auto_week.start()
    print(f"✅ Bot online: {bot.user}")

bot.run(TOKEN)
