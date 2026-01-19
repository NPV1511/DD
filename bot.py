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

# ================== INIT DAY ==================
def init_today(gid):
    attendance.setdefault(gid, {})
    attendance[gid][today()] = {"noon": [], "evening": []}
    save()

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

    @discord.ui.button(label="📍 ĐIỂM DANH", style=discord.ButtonStyle.success)
    async def attend(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = in_session()
        if not session:
            await interaction.response.send_message(
                "⛔ **Chưa đến giờ điểm danh**", ephemeral=True
            )
            return

        gid = str(interaction.guild.id)
        uid = str(interaction.user.id)
        day = today()

        attendance.setdefault(gid, {}).setdefault(day, {"noon": [], "evening": []})

        if any(u["uid"] == uid for u in attendance[gid][day][session]):
            await interaction.response.send_message(
                "⚠️ **Bạn đã điểm danh buổi này rồi**", ephemeral=True
            )
            return

        attendance[gid][day][session].append({
            "uid": uid,
            "time": now().strftime("%H:%M")
        })
        save()

        await interaction.response.send_message("✅ **Điểm danh thành công!**", ephemeral=True)
        await interaction.message.edit(
            embed=build_embed(gid, day),
            view=AttendanceView(gid)
        )

# ================== EMBED ĐẸP ==================
def build_embed(gid, day):
    noon = attendance.get(gid, {}).get(day, {}).get("noon", [])
    evening = attendance.get(gid, {}).get(day, {}).get("evening", [])

    embed = discord.Embed(
        title="📌 BẢNG ĐIỂM DANH HÔM NAY",
        description=(
            f"🗓️ **Ngày:** `{day}`\n"
            f"👥 **Tổng:** `{len(noon) + len(evening)}` người"
        ),
        color=discord.Color.from_rgb(88, 101, 242)
    )

    embed.add_field(
        name=f"🌤️ BUỔI TRƯA ({len(noon)})",
        value="\n".join(
            f"▫️ <@{u['uid']}>  ⏱ `{u['time']}`"
            for u in noon
        ) if noon else "— Chưa có ai điểm danh —",
        inline=False
    )

    embed.add_field(
        name=f"🌙 BUỔI TỐI ({len(evening)})",
        value="\n".join(
            f"▫️ <@{u['uid']}>  ⏱ `{u['time']}`"
            for u in evening
        ) if evening else "— Chưa có ai điểm danh —",
        inline=False
    )

    embed.set_footer(text="Nhấn nút 📍 ĐIỂM DANH bên dưới để tham gia")
    embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/942/942748.png")

    return embed

# ================== COMMAND ==================
@tree.command(name="diemdanh")
@admin_only()
async def diemdanh(interaction: discord.Interaction, channel: discord.TextChannel):
    gid = str(interaction.guild.id)
    attendance_channel[gid] = str(channel.id)
    init_today(gid)
    save()

    await channel.send(
        embed=build_embed(gid, today()),
        view=AttendanceView(gid)
    )
    await interaction.response.send_message("✅ **Đã mở bảng điểm danh**", ephemeral=True)

# ================== TEST THÔNG BÁO ==================
@tree.command(name="testthongbao")
@admin_only()
async def testthongbao(interaction: discord.Interaction, buoi: str):
    gid = str(interaction.guild.id)
    channel = bot.get_channel(int(attendance_channel.get(gid)))

    if not channel:
        await interaction.response.send_message("❌ Chưa set kênh điểm danh", ephemeral=True)
        return

    if buoi not in ["trua", "toi"]:
        await interaction.response.send_message("⚠️ Dùng: trua / toi", ephemeral=True)
        return

    msg = await channel.send(
        f"📢 **MỞ ĐIỂM DANH {buoi.upper()}**\n⏰ Thời gian đang mở!"
    )
    await interaction.response.send_message("✅ Đã test thông báo", ephemeral=True)
    await asyncio.sleep(60)
    await msg.delete()

# ================== AUTO THÔNG BÁO ==================
@tasks.loop(minutes=1)
async def auto_notify():
    t = now().strftime("%H:%M")

    for gid, ch_id in attendance_channel.items():
        channel = bot.get_channel(int(ch_id))
        if not channel:
            continue

        if t == "12:00":
            msg = await channel.send("📢 **MỞ BẢNG ĐIỂM DANH TRƯA** (60s)")
            await asyncio.sleep(60)
            await msg.delete()

        if t == "18:00":
            msg = await channel.send("📢 **MỞ BẢNG ĐIỂM DANH TỐI** (60s)")
            await asyncio.sleep(60)
            await msg.delete()

# ================== DAILY RESET ==================
@tasks.loop(minutes=1)
async def daily_reset():
    if now().strftime("%H:%M") != "00:00":
        return

    for gid, ch_id in attendance_channel.items():
        channel = bot.get_channel(int(ch_id))
        if not channel:
            continue

        init_today(gid)
        await channel.send(
            embed=build_embed(gid, today()),
            view=AttendanceView(gid)
        )

# ================== READY ==================
@bot.event
async def on_ready():
    await tree.sync()
    auto_notify.start()
    daily_reset.start()
    print(f"✅ Bot online: {bot.user}")

bot.run(TOKEN)
