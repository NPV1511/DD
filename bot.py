import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta
import pytz
import json
import os

# ================= CONFIG =================
TOKEN = os.getenv("TOKEN")
if not TOKEN:
    raise RuntimeError("❌ Thiếu TOKEN")

TZ = pytz.timezone("Asia/Ho_Chi_Minh")
DATA_FILE = "data.json"

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ================= TIME =================
def now():
    return datetime.now(TZ)

def today():
    return now().strftime("%Y-%m-%d")

def monday_of_week():
    d = now().date()
    return d - timedelta(days=d.weekday())

# ================= DATA =================
def load():
    if not os.path.exists(DATA_FILE):
        return {
            "attendance_live": {},
            "attendance_log": {},
            "attendance_channel": {},
            "weekly_channel": {},
            "role_theodoi": {}
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

data = load()
attendance_live = data["attendance_live"]
attendance_log = data["attendance_log"]

# ================= VIEW =================
class AttendView(discord.ui.View):
    def __init__(self, gid):
        super().__init__(timeout=None)
        self.gid = str(gid)

    async def attend(self, interaction, session):
        uid = str(interaction.user.id)
        gid = self.gid

        role_id = data["role_theodoi"].get(gid)
        if role_id:
            role = interaction.guild.get_role(role_id)
            if role and role not in interaction.user.roles:
                return await interaction.response.send_message(
                    "❌ Bạn không thuộc role theo dõi", ephemeral=True
                )

        attendance_live.setdefault(gid, {"noon": [], "evening": []})
        attendance_log.setdefault(gid, {}).setdefault(today(), {"noon": [], "evening": []})

        if uid in attendance_live[gid][session]:
            return await interaction.response.send_message(
                "⚠️ Bạn đã điểm danh rồi", ephemeral=True
            )

        attendance_live[gid][session].append(uid)
        attendance_log[gid][today()][session].append(uid)
        save()

        await update_board(interaction.guild)
        await interaction.response.send_message("✅ Điểm danh thành công", ephemeral=True)

    @discord.ui.button(label="🍱 Điểm danh Trưa", style=discord.ButtonStyle.success)
    async def noon(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.attend(interaction, "noon")

    @discord.ui.button(label="🌙 Điểm danh Tối", style=discord.ButtonStyle.primary)
    async def evening(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.attend(interaction, "evening")

# ================= EMBED =================
async def update_board(guild):
    gid = str(guild.id)
    ch_id = data["attendance_channel"].get(gid)
    if not ch_id:
        return

    channel = guild.get_channel(ch_id)
    if not channel:
        return

    async for msg in channel.history(limit=5):
        if msg.author == bot.user:
            noon = attendance_live.get(gid, {}).get("noon", [])
            evening = attendance_live.get(gid, {}).get("evening", [])

            embed = discord.Embed(
                title="📋 BẢNG ĐIỂM DANH HÔM NAY",
                description=f"📅 {now().strftime('%d/%m/%Y')}",
                color=0x2ecc71
            )

            embed.add_field(
                name="🍱 Trưa",
                value="\n".join(f"<@{u}>" for u in noon) or "—",
                inline=True
            )
            embed.add_field(
                name="🌙 Tối",
                value="\n".join(f"<@{u}>" for u in evening) or "—",
                inline=True
            )

            await msg.edit(embed=embed, view=AttendView(guild.id))
            break

# ================= AUTO NOTIFY =================
@tasks.loop(minutes=1)
async def auto_notify():
    hm = now().strftime("%H:%M")

    for gid, ch_id in data["attendance_channel"].items():
        guild = bot.get_guild(int(gid))
        channel = guild.get_channel(ch_id)

        if hm == "12:00":
            m = await channel.send("@everyone 🍱 **MỞ BẢNG ĐIỂM DANH TRƯA**")
            await m.delete(delay=60)

        if hm == "18:00":
            m = await channel.send("@everyone 🌙 **MỞ BẢNG ĐIỂM DANH TỐI**")
            await m.delete(delay=60)

# ================= RESET DAY =================
@tasks.loop(minutes=1)
async def auto_reset_day():
    if now().strftime("%H:%M") != "00:00":
        return

    for gid in attendance_live:
        attendance_live[gid] = {"noon": [], "evening": []}

    save()
    print("🧹 Clean bảng điểm danh ngày mới")

# ================= WEEKLY SUMMARY =================
@tasks.loop(minutes=1)
async def weekly_summary():
    if now().weekday() != 6 or now().strftime("%H:%M") != "23:59":
        return

    for gid, ch_id in data["weekly_channel"].items():
        guild = bot.get_guild(int(gid))
        channel = guild.get_channel(ch_id)

        role_id = data["role_theodoi"].get(gid)
        role = guild.get_role(role_id) if role_id else None

        total = {}
        start = monday_of_week().strftime("%Y-%m-%d")

        for day, sessions in attendance_log.get(gid, {}).items():
            if day < start:
                continue
            for s in sessions.values():
                for uid in s:
                    if role and guild.get_member(int(uid)) not in role.members:
                        continue
                    total[uid] = total.get(uid, 0) + 1

        embed1 = discord.Embed(title="📊 TỔNG ĐIỂM DANH TUẦN", color=0x3498db)
        for u, c in total.items():
            embed1.add_field(name=f"<@{u}>", value=f"{c} buổi", inline=False)

        embed2 = discord.Embed(title="⚠️ DƯỚI 5 BUỔI (CẦN XỬ LÝ)", color=0xe74c3c)
        for u, c in total.items():
            if c < 5:
                embed2.add_field(name=f"<@{u}>", value=f"{c} buổi", inline=False)

        await channel.send(embed=embed1)
        await channel.send(embed=embed2)

        # 🧹 XOÁ TUẦN CŨ
        cutoff = start
        for day in list(attendance_log.get(gid, {})):
            if day < cutoff:
                del attendance_log[gid][day]

        save()

# ================= SLASH =================
@tree.command(name="setrole", description="Set role theo dõi điểm danh")
@app_commands.describe(role="Role theo dõi")
async def setrole(interaction: discord.Interaction, role: discord.Role):
    gid = str(interaction.guild.id)
    data["role_theodoi"][gid] = role.id
    save()
    await interaction.response.send_message(f"✅ Đã set role {role.mention}", ephemeral=True)

@tree.command(name="testevery", description="Test thông báo điểm danh")
async def testevery(interaction: discord.Interaction):
    await interaction.response.send_message("🧪 Test thông báo OK", ephemeral=True)

# ================= READY =================
@bot.event
async def on_ready():
    await tree.sync()
    auto_notify.start()
    auto_reset_day.start()
    weekly_summary.start()
    print(f"✅ Bot online: {bot.user}")

bot.run(TOKEN)
