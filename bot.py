import discord
from discord.ext import commands, tasks
from discord import app_commands
from datetime import datetime, timedelta, time as dtime
import pytz
import json
import os
import asyncio

# ================== CONFIG ==================
TOKEN = os.getenv("TOKEN") or "PUT_TOKEN_HERE"
TZ = pytz.timezone("Asia/Ho_Chi_Minh")
DATA_FILE = "attendance.json"

# ================== BOT ==================
intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ================== DATA ==================
def load():
    if not os.path.exists(DATA_FILE):
        return {
            "attendance": {},
            "attendance_channel": {},
            "history_channel": {},
            "watch_role": {},
            "seo_role": {}
        }
    return json.load(open(DATA_FILE, encoding="utf-8"))

def save():
    json.dump(data, open(DATA_FILE, "w", encoding="utf-8"),
              indent=2, ensure_ascii=False)

data = load()
attendance = data["attendance"]
attendance_channel = data["attendance_channel"]
history_channel = data["history_channel"]
watch_role = data["watch_role"]
seo_role = data["seo_role"]

# ================== TIME ==================
def now():
    return datetime.now(TZ)

def today():
    return now().strftime("%Y-%m-%d")

def week_days():
    base = now() - timedelta(days=now().weekday() + 1)
    return [(base + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]

def current_session():
    t = now().time()
    if dtime(12, 0) <= t <= dtime(16, 0):
        return "noon"
    if dtime(18, 0) <= t <= dtime(22, 0):
        return "evening"
    return None

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
        title="📌 ĐIỂM DANH",
        description=f"📅 Ngày **{day}**",
        color=discord.Color.blurple()
    )

    embed.add_field(
        name="🌤️ BUỔI TRƯA (12:00 – 16:00)",
        value="\n".join(f"{i}. <@{u['uid']}>" for i, u in enumerate(noon, 1))
        if noon else "📭 Chưa có ai",
        inline=False
    )

    embed.add_field(
        name="🌙 BUỔI TỐI (18:00 – 22:00)",
        value="\n".join(f"{i}. <@{u['uid']}>" for i, u in enumerate(evening, 1))
        if evening else "📭 Chưa có ai",
        inline=False
    )

    embed.set_footer(text="Mỗi buổi điểm danh 1 lần")
    return embed

# ================== VIEW ==================
class AttendanceView(discord.ui.View):
    def __init__(self, gid):
        super().__init__(timeout=None)
        self.gid = gid

    @discord.ui.button(label="📍 Điểm danh", style=discord.ButtonStyle.success)
    async def attend(self, interaction: discord.Interaction, _):
        session = current_session()
        if not session:
            return await interaction.response.send_message(
                "⛔ Ngoài giờ điểm danh", ephemeral=True
            )

        gid = self.gid
        uid = str(interaction.user.id)
        day = today()

        attendance.setdefault(gid, {}).setdefault(day, {}) \
                  .setdefault("noon", [])
        attendance[gid][day].setdefault("evening", [])

        if any(u["uid"] == uid for u in attendance[gid][day][session]):
            return await interaction.response.send_message(
                "⚠️ Bạn đã điểm danh buổi này", ephemeral=True
            )

        attendance[gid][day][session].append({
            "uid": uid,
            "time": now().strftime("%H:%M")
        })
        save()

        await interaction.response.send_message("✅ Điểm danh thành công", ephemeral=True)
        await interaction.message.edit(
            embed=build_embed(gid, day),
            view=self
        )

# ================== COMMAND ==================
@tree.command(name="diemdanh", description="Tạo bảng điểm danh")
@admin_only()
async def diemdanh(interaction, channel: discord.TextChannel):
    gid = str(interaction.guild.id)
    attendance_channel[gid] = str(channel.id)
    save()

    await channel.send(
        embed=build_embed(gid, today()),
        view=AttendanceView(gid)
    )
    await interaction.response.send_message("✅ Đã tạo bảng điểm danh", ephemeral=True)

# ================== XỬ LÝ TUẦN ==================
async def handle_week(guild, channel, target=None):
    gid = str(guild.id)
    role_watch = guild.get_role(int(watch_role[gid]))
    role_main = guild.get_role(int(seo_role[gid]["main"]))
    role_sub = guild.get_role(int(seo_role[gid]["sub"]))

    users = [target] if target else role_watch.members
    fail = []

    for member in users:
        total = 0
        for d in week_days():
            day = attendance.get(gid, {}).get(d, {})
            for s in ("noon", "evening"):
                if any(u["uid"] == str(member.id) for u in day.get(s, [])):
                    total += 1

        if total < 5:
            fail.append(member.mention)
            if role_main in member.roles:
                await member.add_roles(role_sub)
            else:
                await member.add_roles(role_main)

    if fail:
        await channel.send(
            "\n".join(fail) +
            "\n⚠️ Nhắc nhở bạn không đủ 5 buổi điểm danh 1 tuần\n"
            "Vui lòng vào <#1462742560274382952> đóng tiền để được xóa sẹo"
        )

# ================== ADMIN COMMAND ==================
@tree.command(name="xuly")
@admin_only()
async def xuly(interaction, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    await handle_week(interaction.guild, channel)
    await interaction.followup.send("✅ Đã xử lý tuần", ephemeral=True)

@tree.command(name="testxuly")
@admin_only()
async def testxuly(interaction, member: discord.Member, channel: discord.TextChannel):
    await interaction.response.defer(ephemeral=True)
    await handle_week(interaction.guild, channel, member)
    await interaction.followup.send("🧪 Test xong", ephemeral=True)

# ================== AUTO TASK ==================
@tasks.loop(minutes=1)
async def auto_task():
    t = now()

    if t.strftime("%H:%M") in ("12:00", "18:00"):
        for gid, cid in attendance_channel.items():
            ch = bot.get_channel(int(cid))
            msg = await ch.send("@everyone ⏰ Mở điểm danh (1 phút tự xoá)")
            await asyncio.sleep(60)
            await msg.delete()

    if t.weekday() == 5 and t.strftime("%H:%M") == "23:59":
        for gid, cid in history_channel.items():
            guild = bot.get_guild(int(gid))
            await handle_week(guild, bot.get_channel(int(cid)))

    if t.weekday() == 6 and t.strftime("%H:%M") == "00:00":
        attendance.clear()
        save()

# ================== READY ==================
@bot.event
async def on_ready():
    await tree.sync()
    auto_task.start()
    print("✅ BOT ONLINE")

bot.run(TOKEN)
