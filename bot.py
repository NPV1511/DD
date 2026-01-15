import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, time as dtime
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
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

attendance = load()

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

        # Chặn trùng trong cùng buổi
        if any(u["uid"] == uid for u in attendance[gid][day][session]):
            await interaction.response.send_message(
                "⚠️ Bạn đã điểm danh buổi này rồi", ephemeral=True
            )
            return

        attendance[gid][day][session].append({
            "uid": uid,
            "time": now().strftime("%H:%M")
        })
        save(attendance)

        await interaction.response.send_message("✅ Điểm danh thành công", ephemeral=True)
        await interaction.message.edit(
            embed=build_embed(gid),
            view=AttendanceView(gid)
        )

# ================== EMBED ==================
def build_embed(gid):
    day = today()
    noon = attendance.get(gid, {}).get(day, {}).get("noon", [])
    evening = attendance.get(gid, {}).get(day, {}).get("evening", [])

    embed = discord.Embed(
        title="📌 ĐIỂM DANH",
        description=f"📅 Ngày: **{day}**",
        color=discord.Color.blurple()
    )

    # TRƯA
    if noon:
        embed.add_field(
            name="🌤️ BUỔI TRƯA (12:00 – 16:00)",
            value="\n".join(
                f"**{i}.** <@{u['uid']}> — `{u['time']}`"
                for i, u in enumerate(noon, 1)
            ),
            inline=False
        )
    else:
        embed.add_field(
            name="🌤️ BUỔI TRƯA (12:00 – 16:00)",
            value="📭 Chưa có ai điểm danh",
            inline=False
        )

    # TỐI
    if evening:
        embed.add_field(
            name="🌙 BUỔI TỐI (18:00 – 22:00)",
            value="\n".join(
                f"**{i}.** <@{u['uid']}> — `{u['time']}`"
                for i, u in enumerate(evening, 1)
            ),
            inline=False
        )
    else:
        embed.add_field(
            name="🌙 BUỔI TỐI (18:00 – 22:00)",
            value="📭 Chưa có ai điểm danh",
            inline=False
        )

    total = len(noon) + len(evening)
    embed.set_footer(text=f"👥 Tổng hôm nay: {total} | Mỗi buổi 1 lần / người")

    return embed

# ================== COMMAND ==================
@tree.command(name="diemdanh", description="Tạo bảng điểm danh")
@admin_only()
async def diemdanh(interaction: discord.Interaction):
    gid = str(interaction.guild.id)
    await interaction.response.send_message(
        embed=build_embed(gid),
        view=AttendanceView(gid)
    )

@tree.command(name="testdiemdanh", description="Test điểm danh trưa / tối")
@admin_only()
@app_commands.choices(buoi=[
    app_commands.Choice(name="Trưa", value="noon"),
    app_commands.Choice(name="Tối", value="evening"),
])
async def testdiemdanh(interaction: discord.Interaction, buoi: app_commands.Choice[str]):
    gid = str(interaction.guild.id)
    await interaction.response.send_message(
        embed=build_embed(gid),
        view=AttendanceView(gid),
        ephemeral=True
    )

@tree.command(name="testlichsu", description="Xem lịch sử hôm nay")
@admin_only()
async def testlichsu(interaction: discord.Interaction, channel: discord.TextChannel):
    gid = str(interaction.guild.id)
    embed = build_embed(gid)
    await channel.send(embed=embed)
    await interaction.response.send_message("✅ Đã gửi lịch sử", ephemeral=True)

@tree.command(name="testenday", description="Kết thúc ngày + gửi lịch sử")
@admin_only()
async def testenday(interaction: discord.Interaction, channel: discord.TextChannel):
    gid = str(interaction.guild.id)
    embed = build_embed(gid)
    await channel.send(embed=embed)

    attendance.get(gid, {}).pop(today(), None)
    save(attendance)

    await interaction.response.send_message(
        "🔚 Đã kết thúc ngày & reset dữ liệu",
        ephemeral=True
    )

# ================== RESET AUTO ==================
@tasks.loop(minutes=1)
async def auto_reset():
    if now().strftime("%H:%M") == "00:00":
        for gid in attendance:
            attendance[gid].pop(today(), None)
        save(attendance)
        print("🔄 Reset ngày mới")

# ================== READY ==================
@bot.event
async def on_ready():
    await tree.sync()
    auto_reset.start()
    print(f"✅ Bot online: {bot.user}")

bot.run(TOKEN)
