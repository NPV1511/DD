import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta, time as dtime
import pytz, os, json, asyncio

# ================= ENV =================
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("❌ Thiếu TOKEN")

TZ = pytz.timezone("Asia/Ho_Chi_Minh")
DATA_FILE = "attendance.json"

# ================= DATA =================
def load():
    if not os.path.exists(DATA_FILE):
        return {
            "attendance_live": {},
            "attendance_log": {},
            "attendance_channel": {},
            "history_channel": {},
            "weekly_channel": {},
            "role_theodoi": {}
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

data = load()

# ================= TIME =================
def now():
    return datetime.now(TZ)

def today():
    return now().strftime("%Y-%m-%d")

def monday():
    d = now().date()
    return (d - timedelta(days=d.weekday())).strftime("%Y-%m-%d")

# ================= BOT =================
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ================= PERMISSION =================
def admin_only():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)

# ================= VIEW =================
class AttendView(discord.ui.View):
    def __init__(self, gid):
        super().__init__(timeout=None)
        self.gid = str(gid)

    @discord.ui.button(label="🍱 Điểm danh Trưa", style=discord.ButtonStyle.success)
    async def noon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await attend(interaction, "noon")

    @discord.ui.button(label="🌙 Điểm danh Tối", style=discord.ButtonStyle.primary)
    async def evening(self, interaction: discord.Interaction, button: discord.ui.Button):
        await attend(interaction, "evening")

# ================= ATTEND =================
async def attend(interaction, session):
    gid = str(interaction.guild.id)
    uid = str(interaction.user.id)

    role_id = data["role_theodoi"].get(gid)
    if role_id:
        role = interaction.guild.get_role(role_id)
        if role and role not in interaction.user.roles:
            return await interaction.response.send_message(
                "❌ Bạn không thuộc role theo dõi", ephemeral=True
            )

    data["attendance_live"].setdefault(gid, {"noon": [], "evening": []})
    data["attendance_log"].setdefault(gid, {}).setdefault(today(), {"noon": [], "evening": []})

    if uid in data["attendance_live"][gid][session]:
        return await interaction.response.send_message(
            "⚠️ Bạn đã điểm danh rồi", ephemeral=True
        )

    data["attendance_live"][gid][session].append(uid)
    data["attendance_log"][gid][today()][session].append(uid)
    save()

    await update_board(interaction.guild)
    await interaction.response.send_message("✅ Điểm danh thành công", ephemeral=True)

# ================= EMBED =================
async def update_board(guild):
    gid = str(guild.id)
    cid = data["attendance_channel"].get(gid)
    if not cid:
        return

    channel = guild.get_channel(int(cid))
    if not channel:
        return

    noon = data["attendance_live"].get(gid, {}).get("noon", [])
    evening = data["attendance_live"].get(gid, {}).get("evening", [])

    embed = discord.Embed(
        title="📋 BẢNG ĐIỂM DANH",
        description=f"📅 {today()}",
        color=0x2ecc71
    )

    embed.add_field(name="🍱 Trưa", value="\n".join(f"<@{u}>" for u in noon) or "—", inline=False)
    embed.add_field(name="🌙 Tối", value="\n".join(f"<@{u}>" for u in evening) or "—", inline=False)

    async for msg in channel.history(limit=5):
        if msg.author == bot.user:
            await msg.edit(embed=embed, view=AttendView(gid))
            return

    await channel.send(embed=embed, view=AttendView(gid))

# ================= AUTO =================
@tasks.loop(seconds=30)
async def auto_notify():
    hm = now().strftime("%H:%M")
    for gid, cid in data["attendance_channel"].items():
        channel = bot.get_channel(int(cid))
        if not channel:
            continue

        if hm == "12:00":
            m = await channel.send("@everyone 🍱 **MỞ ĐIỂM DANH TRƯA**")
            await m.delete(delay=60)

        if hm == "18:00":
            m = await channel.send("@everyone 🌙 **MỞ ĐIỂM DANH TỐI**")
            await m.delete(delay=60)

@tasks.loop(minutes=1)
async def reset_day():
    if now().strftime("%H:%M") != "00:00":
        return
    for gid in data["attendance_live"]:
        data["attendance_live"][gid] = {"noon": [], "evening": []}
    save()

# ================= SLASH =================
@tree.command(name="diemdanh", description="Gửi bảng điểm danh")
@admin_only()
async def diemdanh(interaction: discord.Interaction, channel: discord.TextChannel):
    data["attendance_channel"][str(interaction.guild.id)] = channel.id
    save()
    await update_board(interaction.guild)
    await interaction.response.send_message("✅ Đã tạo bảng điểm danh", ephemeral=True)

@tree.command(name="setrole", description="Set role theo dõi")
@admin_only()
async def setrole(interaction: discord.Interaction, role: discord.Role):
    data["role_theodoi"][str(interaction.guild.id)] = role.id
    save()
    await interaction.response.send_message("✅ Đã set role", ephemeral=True)

@tree.command(name="testthongbao", description="Test thông báo điểm danh")
@admin_only()
async def testthongbao(interaction: discord.Interaction):
    await interaction.response.send_message("🧪 OK", ephemeral=True)

@tree.command(name="testreset", description="Test reset ngày")
@admin_only()
async def testreset(interaction: discord.Interaction):
    for gid in data["attendance_live"]:
        data["attendance_live"][gid] = {"noon": [], "evening": []}
    save()
    await interaction.response.send_message("🧹 Reset OK", ephemeral=True)

@tree.command(name="testevery", description="Test slash command")
async def testevery(interaction: discord.Interaction):
    await interaction.response.send_message("✅ Slash hoạt động", ephemeral=True)

# ================= READY =================
@bot.event
async def on_ready():
    await tree.sync()
    auto_notify.start()
    reset_day.start()
    print("✅ Bot online – slash đầy đủ")

bot.run(TOKEN)
