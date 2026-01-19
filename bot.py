import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
from datetime import datetime
import pytz
import json
import os

# ================== CONFIG ==================
TOKEN = os.getenv("TOKEN") or "YOUR_BOT_TOKEN"
TIMEZONE = pytz.timezone("Asia/Ho_Chi_Minh")

DATA_FILE = "attendance.json"

# ================== BOT ==================
intents = discord.Intents.default()
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ================== DATA ==================
if os.path.exists(DATA_FILE):
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
else:
    data = {}

attendance_channel = data.get("attendance_channel", {})
attendance_data = data.get("attendance_data", {})


def save_data():
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(
            {
                "attendance_channel": attendance_channel,
                "attendance_data": attendance_data
            },
            f,
            indent=4,
            ensure_ascii=False
        )


def now():
    return datetime.now(TIMEZONE)


# ================== PERMISSION ==================
def admin_only():
    async def predicate(interaction: discord.Interaction):
        return interaction.user.guild_permissions.administrator
    return app_commands.check(predicate)


# ================== SEND NOTIFY (PING @EVERYONE) ==================
async def send_notify(channel: discord.TextChannel, content: str):
    return await channel.send(
        content,
        allowed_mentions=discord.AllowedMentions(everyone=True)
    )


# ================== AUTO NOTIFY ==================
@tasks.loop(minutes=1)
async def auto_notify():
    t = now().strftime("%H:%M")

    for gid, ch_id in attendance_channel.items():
        channel = bot.get_channel(int(ch_id))
        if not channel:
            continue

        # ===== 12:00 =====
        if t == "12:00":
            msg = await send_notify(
                channel,
                "@everyone 📢 **MỞ BẢNG ĐIỂM DANH TRƯA**\n"
                "⏰ Thời gian: **12:00 – 16:00**\n"
                "🗑️ Tự xoá sau **60 giây**"
            )
            await asyncio.sleep(60)
            await msg.delete()

        # ===== 18:00 =====
        if t == "18:00":
            msg = await send_notify(
                channel,
                "@everyone 📢 **MỞ BẢNG ĐIỂM DANH TỐI**\n"
                "⏰ Thời gian: **18:00 – 22:00**\n"
                "🗑️ Tự xoá sau **60 giây**"
            )
            await asyncio.sleep(60)
            await msg.delete()


# ================== COMMAND SET CHANNEL ==================
@tree.command(name="diemdanh", description="Set kênh điểm danh")
@admin_only()
async def diemdanh(interaction: discord.Interaction, channel: discord.TextChannel):
    attendance_channel[str(interaction.guild.id)] = str(channel.id)
    save_data()
    await interaction.response.send_message(
        f"✅ Đã set kênh điểm danh: {channel.mention}",
        ephemeral=True
    )


# ================== TEST NOTIFY ==================
@tree.command(name="testthongbao", description="Test thông báo điểm danh")
@admin_only()
@app_commands.describe(buoi="trua hoặc toi")
async def testthongbao(interaction: discord.Interaction, buoi: str):
    gid = str(interaction.guild.id)
    ch_id = attendance_channel.get(gid)

    if not ch_id:
        await interaction.response.send_message(
            "❌ Chưa set kênh điểm danh",
            ephemeral=True
        )
        return

    channel = bot.get_channel(int(ch_id))
    if not channel:
        await interaction.response.send_message("❌ Không tìm thấy channel", ephemeral=True)
        return

    buoi = buoi.lower()
    if buoi not in ["trua", "toi"]:
        await interaction.response.send_message(
            "⚠️ Dùng `/testthongbao trua` hoặc `/testthongbao toi`",
            ephemeral=True
        )
        return

    msg = await send_notify(
        channel,
        f"@everyone 📢 **TEST MỞ ĐIỂM DANH {buoi.upper()}**\n"
        "🗑️ Tự xoá sau **60 giây**"
    )

    await interaction.response.send_message("✅ Test OK", ephemeral=True)
    await asyncio.sleep(60)
    await msg.delete()


# ================== ATTENDANCE BUTTON ==================
class AttendanceView(discord.ui.View):
    def __init__(self, buoi):
        super().__init__(timeout=300)
        self.buoi = buoi

    @discord.ui.button(label="✅ Điểm danh", style=discord.ButtonStyle.green)
    async def checkin(self, interaction: discord.Interaction, button: discord.ui.Button):
        gid = str(interaction.guild.id)
        uid = str(interaction.user.id)
        today = now().strftime("%d/%m/%Y")

        attendance_data.setdefault(gid, {})
        attendance_data[gid].setdefault(uid, {})
        attendance_data[gid][uid].setdefault(today, [])

        if self.buoi in attendance_data[gid][uid][today]:
            await interaction.response.send_message(
                "⚠️ Bạn đã điểm danh rồi",
                ephemeral=True
            )
            return

        attendance_data[gid][uid][today].append(self.buoi)
        save_data()

        await interaction.response.send_message(
            f"✅ Điểm danh **{self.buoi}** thành công!",
            ephemeral=True
        )


# ================== MANUAL OPEN ==================
@tree.command(name="mo", description="Mở bảng điểm danh")
@admin_only()
@app_commands.describe(buoi="trua hoặc toi")
async def mo(interaction: discord.Interaction, buoi: str):
    gid = str(interaction.guild.id)
    ch_id = attendance_channel.get(gid)

    if not ch_id:
        await interaction.response.send_message("❌ Chưa set kênh điểm danh", ephemeral=True)
        return

    channel = bot.get_channel(int(ch_id))
    buoi = buoi.lower()

    if buoi not in ["trua", "toi"]:
        await interaction.response.send_message("⚠️ trua | toi", ephemeral=True)
        return

    embed = discord.Embed(
        title="📋 BẢNG ĐIỂM DANH",
        description=f"🕒 Buổi: **{buoi.upper()}**\n⏳ Mở trong **5 phút**",
        color=discord.Color.green()
    )
    embed.set_footer(text="Nhấn nút bên dưới để điểm danh")

    await channel.send(
        embed=embed,
        view=AttendanceView(buoi)
    )
    await interaction.response.send_message("✅ Đã mở bảng điểm danh", ephemeral=True)


# ================== READY ==================
@bot.event
async def on_ready():
    await tree.sync()
    auto_notify.start()
    print(f"✅ Bot online: {bot.user}")


bot.run(TOKEN)
