import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time as dtime, timedelta
import pytz
import os
import json

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
            "history_channel": {}
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

data = load()
attendance = data["attendance"]
history_channel = data["history_channel"]

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
            await interaction.response.send_message(
                "⛔ Ngoài giờ điểm danh", ephemeral=True
            )
            return

        gid = str(interaction.guild.id)
        uid = str(interaction.user.id)
        day = today()

        attendance.setdefault(gid, {}).setdefault(day, {}).setdefault("noon", [])
        attendance.setdefault(gid, {}).setdefault(day, {}).setdefault("evening", [])

        if any(u["uid"] == uid for u in attendance[gid][day][session]):
            await interaction.response.send_message(
                "⚠️ Bạn đã điểm danh buổi này rồi", ephemeral=True
            )
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
        name="🌤️ BUỔI TRƯA (12:00 – 16:00)",
        value="\n".join(
            f"**{i}.** <@{u['uid']}> — `{u['time']}`"
            for i, u in enumerate(noon, 1)
        ) if noon else "📭 Chưa có ai điểm danh",
        inline=False
    )

    embed.add_field(
        name="🌙 BUỔI TỐI (18:00 – 22:00)",
        value="\n".join(
            f"**{i}.** <@{u['uid']}> — `{u['time']}`"
            for i, u in enumerate(evening, 1)
        ) if evening else "📭 Chưa có ai điểm danh",
        inline=False
    )

    embed.set_footer(
        text=f"👥 Tổng hôm nay: {len(noon) + len(evening)} | Mỗi buổi 1 lần / người"
    )

    return embed

# ================== COMMAND ==================
@tree.command(name="diemdanh", description="Tạo bảng điểm danh")
@admin_only()
async def diemdanh(interaction: discord.Interaction, channel: discord.TextChannel):
    gid = str(interaction.guild.id)
    day = today()

    await channel.send(
        embed=build_embed(gid, day),
        view=AttendanceView(gid)
    )
    await interaction.response.send_message(
        f"✅ Đã gửi bảng điểm danh vào {channel.mention}",
        ephemeral=True
    )

@tree.command(name="kenhlichsu", description="Set kênh gửi lịch sử tự động mỗi ngày")
@admin_only()
async def kenhlichsu(interaction: discord.Interaction, channel: discord.TextChannel):
    history_channel[str(interaction.guild.id)] = str(channel.id)
    save()
    await interaction.response.send_message(
        f"✅ Đã set kênh lịch sử: {channel.mention}",
        ephemeral=True
    )

# ================== AUTO RESET + SEND HISTORY ==================
@tasks.loop(minutes=1)
async def auto_reset():
    if now().strftime("%H:%M") != "00:00":
        return

    yday = yesterday()

    for gid in list(attendance.keys()):
        if gid in history_channel:
            ch = bot.get_channel(int(history_channel[gid]))
            if ch:
                await ch.send(embed=build_embed(gid, yday))

        attendance[gid].pop(yday, None)

    save()
    print("🔄 Reset ngày mới + gửi lịch sử")

# ================== READY ==================
@bot.event
async def on_ready():
    await tree.sync()
    auto_reset.start()
    print(f"✅ Bot online: {bot.user}")

bot.run(TOKEN)
