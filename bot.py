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
            "weekly_channel": {},
            "role_theodoi": {}
        }
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

data = load()
attendance = data["attendance"]
attendance_channel = data["attendance_channel"]
weekly_channel = data["weekly_channel"]
role_theodoi = data["role_theodoi"]

# ================== TIME ==================
def now():
    return datetime.now(tz)

def today():
    return now().strftime("%Y-%m-%d")

def week_range():
    end = now()
    start = end - timedelta(days=6)
    return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

def current_session():
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

# ================== EMBED ==================
def build_embed(gid, day):
    noon = attendance.get(gid, {}).get(day, {}).get("noon", [])
    evening = attendance.get(gid, {}).get(day, {}).get("evening", [])

    embed = discord.Embed(
        title="📌 BẢNG ĐIỂM DANH",
        description=f"📅 **{day}**",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="🌤️ BUỔI TRƯA (12:00–16:00)",
        value="\n".join(
            f"**{i}.** <@{u['uid']}> — `{u['time']}`"
            for i, u in enumerate(noon, 1)
        ) if noon else "📭 Chưa có ai",
        inline=False
    )

    embed.add_field(
        name="🌙 BUỔI TỐI (18:00–22:00)",
        value="\n".join(
            f"**{i}.** <@{u['uid']}> — `{u['time']}`"
            for i, u in enumerate(evening, 1)
        ) if evening else "📭 Chưa có ai",
        inline=False
    )

    embed.set_footer(text=f"Tổng hôm nay: {len(noon) + len(evening)}")
    return embed

# ================== VIEW ==================
class AttendanceView(discord.ui.View):
    def __init__(self, gid):
        super().__init__(timeout=None)
        self.gid = gid

    @discord.ui.button(label="📍 Điểm danh", style=discord.ButtonStyle.success)
    async def attend(self, interaction: discord.Interaction, button: discord.ui.Button):
        session = current_session()
        if not session:
            await interaction.response.send_message("⛔ Ngoài giờ điểm danh", ephemeral=True)
            return

        gid = str(interaction.guild.id)
        uid = str(interaction.user.id)
        day = today()

        attendance.setdefault(gid, {}).setdefault(day, {"noon": [], "evening": []})

        if any(u["uid"] == uid for u in attendance[gid][day][session]):
            await interaction.response.send_message("⚠️ Đã điểm danh rồi", ephemeral=True)
            return

        attendance[gid][day][session].append({
            "uid": uid,
            "time": now().strftime("%H:%M")
        })
        save()

        await interaction.response.send_message("✅ Điểm danh thành công", ephemeral=True)
        await interaction.message.edit(embed=build_embed(gid, day), view=AttendanceView(gid))

# ================== COMMAND ==================
@tree.command(name="diemdanh", description="Tạo bảng điểm danh")
@admin_only()
async def diemdanh(interaction: discord.Interaction, channel: discord.TextChannel):
    gid = str(interaction.guild.id)
    attendance_channel[gid] = str(channel.id)
    attendance.setdefault(gid, {})[today()] = {"noon": [], "evening": []}
    save()

    await channel.send(embed=build_embed(gid, today()), view=AttendanceView(gid))
    await interaction.response.send_message("✅ Đã tạo bảng điểm danh", ephemeral=True)

@tree.command(name="settongtuan", description="Set kênh gửi tổng tuần")
@admin_only()
async def settongtuan(interaction: discord.Interaction, channel: discord.TextChannel):
    weekly_channel[str(interaction.guild.id)] = str(channel.id)
    save()
    await interaction.response.send_message(
        f"✅ Đã set kênh tổng tuần: {channel.mention}", ephemeral=True
    )

@tree.command(name="setroletheodoi", description="Set role theo dõi điểm danh")
@admin_only()
async def setroletheodoi(interaction: discord.Interaction, role: discord.Role):
    role_theodoi[str(interaction.guild.id)] = str(role.id)
    save()
    await interaction.response.send_message(
        f"✅ Đã set role theo dõi: {role.mention}", ephemeral=True
    )

@tree.command(name="testevery", description="Test thông báo mở điểm danh")
@admin_only()
@app_commands.choices(buoi=[
    app_commands.Choice(name="Trưa", value="noon"),
    app_commands.Choice(name="Tối", value="evening"),
])
async def testevery(interaction: discord.Interaction, buoi: app_commands.Choice[str]):
    gid = str(interaction.guild.id)
    channel = bot.get_channel(int(attendance_channel.get(gid, 0)))
    if not channel:
        await interaction.response.send_message("❌ Chưa set kênh điểm danh", ephemeral=True)
        return

    text = "@everyone 🌤️ **MỞ ĐIỂM DANH TRƯA**" if buoi.value == "noon" \
        else "@everyone 🌙 **MỞ ĐIỂM DANH TỐI**"

    msg = await channel.send(text)
    await interaction.response.send_message("✅ Đã test", ephemeral=True)
    await asyncio.sleep(60)
    await msg.delete()

# ================== AUTO NOTIFY ==================
@tasks.loop(seconds=30)
async def auto_notify():
    t = now().strftime("%H:%M")
    for gid, cid in attendance_channel.items():
        ch = bot.get_channel(int(cid))
        if not ch:
            continue
        if t == "12:00":
            m = await ch.send("@everyone 🌤️ **MỞ ĐIỂM DANH TRƯA**")
            await asyncio.sleep(60)
            await m.delete()
        if t == "18:00":
            m = await ch.send("@everyone 🌙 **MỞ ĐIỂM DANH TỐI**")
            await asyncio.sleep(60)
            await m.delete()

# ================== AUTO RESET DAY ==================
@tasks.loop(minutes=1)
async def auto_reset_day():
    if now().strftime("%H:%M") != "00:00":
        return

    day = today()
    for gid, cid in attendance_channel.items():
        attendance.setdefault(gid, {})[day] = {"noon": [], "evening": []}
        ch = bot.get_channel(int(cid))
        if not ch:
            continue

        async for msg in ch.history(limit=5):
            if msg.author == bot.user and msg.embeds:
                await msg.edit(embed=build_embed(gid, day), view=AttendanceView(gid))
                break

    save()
    print("🧹 Reset bảng điểm danh ngày mới")

# ================== AUTO WEEKLY SUMMARY ==================
@tasks.loop(minutes=1)
async def weekly_summary():
    if now().weekday() != 6 or now().strftime("%H:%M") != "23:59":
        return

    start, end = week_range()

    for guild in bot.guilds:
        gid = str(guild.id)
        if gid not in weekly_channel or gid not in role_theodoi:
            continue

        role = guild.get_role(int(role_theodoi[gid]))
        if not role:
            continue

        counter = {}

        for day, sessions in attendance.get(gid, {}).items():
            if start <= day <= end:
                for s in ["noon", "evening"]:
                    for u in sessions.get(s, []):
                        member = guild.get_member(int(u["uid"]))
                        if member and role in member.roles:
                            counter[u["uid"]] = counter.get(u["uid"], 0) + 1

        embed = discord.Embed(
            title="📊 TỔNG ĐIỂM DANH TUẦN",
            description=f"Từ **{start}** đến **{end}**",
            color=discord.Color.gold()
        )

        embed.add_field(
            name="📋 TỔNG TẤT CẢ",
            value="\n".join(
                f"<@{uid}> — **{c} buổi**" for uid, c in counter.items()
            ) or "Không có",
            inline=False
        )

        embed.add_field(
            name="⚠️ DƯỚI 5 BUỔI (CẦN XỬ LÝ)",
            value="\n".join(
                f"<@{uid}> — **{c} buổi** ❗"
                for uid, c in counter.items() if c < 5
            ) or "Không có",
            inline=False
        )

        await bot.get_channel(int(weekly_channel[gid])).send(embed=embed)

# ================== READY ==================
@bot.event
async def on_ready():
    await tree.sync()
    auto_notify.start()
    auto_reset_day.start()
    weekly_summary.start()
    print(f"✅ Bot online: {bot.user}")

bot.run(TOKEN)

