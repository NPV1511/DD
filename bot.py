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
            "watch_role": {},
            "seo_role": {}
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
watch_role = data["watch_role"]
seo_role = data["seo_role"]

# ================== TIME ==================
def now():
    return datetime.now(tz)

def today():
    return now().strftime("%Y-%m-%d")

def yesterday():
    return (now() - timedelta(days=1)).strftime("%Y-%m-%d")

def week_days():
    start = now() - timedelta(days=now().weekday())
    return [(start + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

def in_session():
    t = now().time()
    if dtime(12, 0) <= t <= dtime(16, 0):
        return "noon"
    if dtime(18, 0) <= t <= dtime(22, 0):
        return "evening"
    return None

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
    async def attend(self, interaction: discord.Interaction, _):
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
        await interaction.message.edit(embed=build_embed(gid, day), view=AttendanceView(gid))

# ================== EMBED ==================
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
        value="\n".join(f"{i}. <@{u['uid']}> — `{u['time']}`" for i, u in enumerate(noon, 1))
        if noon else "📭 Chưa có ai",
        inline=False
    )

    embed.add_field(
        name="🌙 BUỔI TỐI",
        value="\n".join(f"{i}. <@{u['uid']}> — `{u['time']}`" for i, u in enumerate(evening, 1))
        if evening else "📭 Chưa có ai",
        inline=False
    )

    embed.set_footer(text=f"Tổng hôm nay: {len(noon) + len(evening)}")
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

@tree.command(name="kenhlichsu")
@admin_only()
async def kenhlichsu(interaction: discord.Interaction, channel: discord.TextChannel):
    history_channel[str(interaction.guild.id)] = str(channel.id)
    save()
    await interaction.response.send_message("✅ Đã set kênh lịch sử", ephemeral=True)

@tree.command(name="roledd")
@admin_only()
async def roledd(interaction: discord.Interaction, role: discord.Role):
    watch_role[str(interaction.guild.id)] = str(role.id)
    save()
    await interaction.response.send_message("✅ Đã set role theo dõi", ephemeral=True)

@tree.command(name="roleseo")
@admin_only()
async def roleseo(interaction: discord.Interaction, rolechinh: discord.Role, rolephu: discord.Role):
    seo_role[str(interaction.guild.id)] = {
        "main": str(rolechinh.id),
        "sub": str(rolephu.id)
    }
    save()
    await interaction.response.send_message("✅ Đã set role sẹo", ephemeral=True)

# ================== HANDLE WEEK ==================
async def handle_week(guild: discord.Guild, channel: discord.TextChannel):
    gid = str(guild.id)
    if gid not in watch_role or gid not in seo_role:
        return

    role_watch = guild.get_role(int(watch_role[gid]))
    role_main = guild.get_role(int(seo_role[gid]["main"]))
    role_sub = guild.get_role(int(seo_role[gid]["sub"]))

    violators = []

    for member in role_watch.members:
        count = 0
        for d in week_days():
            for s in ["noon", "evening"]:
                if any(
                    u["uid"] == str(member.id)
                    for u in attendance.get(gid, {}).get(d, {}).get(s, [])
                ):
                    count += 1

        if count < 5:
            violators.append((member, count))
            if role_main in member.roles:
                await member.add_roles(role_sub)
            else:
                await member.add_roles(role_main)

    if violators:
        await channel.send(
            "\n".join(f"{m.mention} ({c}/5)" for m, c in violators)
            + "\n\n⚠️ Nhắc nhở bạn không đủ 5 buổi điểm danh 1 tuần\n"
              "Vui lòng vào <#1462742560274382952> đóng tiền để được xóa sẹo"
        )

@tree.command(name="xuly")
@admin_only()
async def xuly(interaction: discord.Interaction, channel: discord.TextChannel):
    await handle_week(interaction.guild, channel)
    await interaction.response.send_message("✅ Đã xử lý tuần", ephemeral=True)

@tree.command(name="testxuly")
@admin_only()
async def testxuly(interaction: discord.Interaction, member: discord.Member, channel: discord.TextChannel):
    await handle_week(interaction.guild, channel)
    await interaction.response.send_message("🧪 Đã test xử lý", ephemeral=True)

# ================== AUTO XỬ LÝ THỨ 7 ==================
@tasks.loop(minutes=1)
async def auto_xuly_week():
    t = now()
    if t.weekday() != 5 or t.strftime("%H:%M") != "23:59":
        return

    for gid, cid in history_channel.items():
        guild = bot.get_guild(int(gid))
        channel = bot.get_channel(int(cid))
        if guild and channel:
            await handle_week(guild, channel)

# ================== AUTO RESET TUẦN ==================
@tasks.loop(minutes=1)
async def auto_reset_week():
    t = now()
    if t.weekday() != 6 or t.strftime("%H:%M") != "00:00":
        return

    for gid in attendance:
        for d in week_days():
            attendance[gid].pop(d, None)

    save()
    print("🧹 Reset tuần hoàn tất")

# ================== READY ==================
@bot.event
async def on_ready():
    await tree.sync()
    auto_xuly_week.start()
    auto_reset_week.start()
    print(f"✅ Bot online: {bot.user}")

bot.run(TOKEN)
