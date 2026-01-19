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
            "history_channel": {},
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
history_channel = data["history_channel"]
attendance_channel = data["attendance_channel"]
weekly_summary_channel = data["weekly_summary_channel"]
weekly_summary_role = data["weekly_summary_role"]

# ================== TIME ==================
def now():
    return datetime.now(tz)

def today():
    return now().strftime("%Y-%m-%d")

def yesterday():
    return (now() - timedelta(days=1)).strftime("%Y-%m-%d")

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

    embed = discord.Embed(
        title="📌 ĐIỂM DANH",
        description=f"📅 Ngày: **{day}**",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="🌤️ BUỔI TRƯA",
        value="\n".join(
            f"{i}. <@{u['uid']}> — `{u['time']}`"
            for i, u in enumerate(noon, 1)
        ) if noon else "Chưa có",
        inline=False
    )

    embed.add_field(
        name="🌙 BUỔI TỐI",
        value="\n".join(
            f"{i}. <@{u['uid']}> — `{u['time']}`"
            for i, u in enumerate(evening, 1)
        ) if evening else "Chưa có",
        inline=False
    )

    return embed

# ================== EMBED TUẦN ==================
def build_week_attendance_tables(gid, role: discord.Role):
    dates = week_dates()
    user_count = {}

    for day in dates:
        day_data = attendance.get(gid, {}).get(day, {})
        for session in ["noon", "evening"]:
            for u in day_data.get(session, []):
                user_count[u["uid"]] = user_count.get(u["uid"], 0) + 1

    role_members = {str(m.id): m for m in role.members}

    full_list = []
    under_5_list = []

    for uid, total in user_count.items():
        if uid not in role_members:
            continue
        member = role_members[uid]
        full_list.append((member, total))
        if total < 5:
            under_5_list.append((member, total))

    full_list.sort(key=lambda x: x[1], reverse=True)
    under_5_list.sort(key=lambda x: x[1])

    embed = discord.Embed(
        title="📊 BẢNG TỔNG ĐIỂM DANH",
        description=f"📅 Từ **{dates[0]}** đến **{dates[-1]}**\n👀 Role theo dõi: {role.mention}",
        color=discord.Color.orange()
    )

    embed.add_field(
        name="🟦 Tổng điểm danh",
        value="\n".join(
            f"• {m.mention} — **{t} buổi**"
            for m, t in full_list
        ) if full_list else "Không có dữ liệu",
        inline=False
    )

    embed.add_field(
        name="🟥 Dưới 5 buổi (cần xử lý)",
        value="\n".join(
            f"• {m.mention} — **{t} buổi** ⚠️"
            for m, t in under_5_list
        ) if under_5_list else "Không có",
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
    await interaction.response.send_message("✅ Đã gửi bảng điểm danh", ephemeral=True)

@tree.command(name="tongtuan")
@admin_only()
async def tongtuan(interaction: discord.Interaction, channel: discord.TextChannel, roletheodoi: discord.Role):
    gid = str(interaction.guild.id)
    embed = build_week_attendance_tables(gid, roletheodoi)
    await channel.send(embed=embed)
    await interaction.response.send_message("✅ Đã gửi bảng tổng tuần", ephemeral=True)

@tree.command(name="settongtuan")
@admin_only()
async def settongtuan(interaction: discord.Interaction, channel: discord.TextChannel, roletheodoi: discord.Role):
    gid = str(interaction.guild.id)
    weekly_summary_channel[gid] = str(channel.id)
    weekly_summary_role[gid] = str(roletheodoi.id)
    save()
    await interaction.response.send_message("✅ Đã set auto tổng tuần (23:59 Thứ 7)", ephemeral=True)

# ================== AUTO WEEK ==================
@tasks.loop(minutes=1)
async def auto_weekly_summary():
    n = now()
    if n.weekday() != 5 or n.strftime("%H:%M") != "23:59":
        return

    for gid, ch_id in weekly_summary_channel.items():
        channel = bot.get_channel(int(ch_id))
        if not channel:
            continue
        role = channel.guild.get_role(int(weekly_summary_role.get(gid)))
        if not role:
            continue

        embed = build_week_attendance_tables(gid, role)
        await channel.send(embed=embed)

# ================== READY ==================
@bot.event
async def on_ready():
    await tree.sync()
    auto_weekly_summary.start()
    print(f"✅ Bot online: {bot.user}")

bot.run(TOKEN)
