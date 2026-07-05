"""Valfri Discord-textbot för Game Voice Helper.

Skriv `!fraga hur öppnar jag dörren?` i en Discord-kanal så skickas frågan
(plus senaste bildrutan från din Twitch-ström) till den lokala servern och
svaret postas i kanalen.

OBS: Detta är en TEXT-bot. Discord-röst (tala/lyssna i röstkanal) är medvetet
inte med i MVP:n — se README → Roadmap. Använd webbklientens push-to-talk för
röst så länge.

Kräver: pip install discord.py  +  DISCORD_BOT_TOKEN i miljön.
Servern (server.py) måste vara igång.
"""

import os

import discord
import requests

SERVER = os.environ.get("GAME_HELPER_SERVER", "http://localhost:8000")
TOKEN = os.environ["DISCORD_BOT_TOKEN"]

intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

PREFIXES = {
    "!fraga": "ledtrad",
    "!ledtrad": "ledtrad",
    "!svar": "direkt",
    "!kontroller": "kontroller",
}


@client.event
async def on_ready():
    print(f"Inloggad som {client.user} — skriv !fraga <din fråga> i en kanal.")


@client.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return
    parts = message.content.split(maxsplit=1)
    if not parts or parts[0].lower() not in PREFIXES:
        return
    if len(parts) < 2 or not parts[1].strip():
        await message.reply("Skriv din fråga efter kommandot, t.ex. `!fraga var hittar jag skruvmejseln?`")
        return

    mode = PREFIXES[parts[0].lower()]
    async with message.channel.typing():
        try:
            r = requests.post(
                f"{SERVER}/api/ask",
                json={"fraga": parts[1].strip(), "mode": mode, "use_stream": True},
                timeout=120,
            )
            data = r.json()
            if not r.ok:
                await message.reply(f"⚠️ {data.get('detail', r.status_code)}")
                return
            badge = {"twitch": "📺", "uppladdad": "🖼️", "ingen": "👁️‍🗨️"}.get(data["bildkalla"], "")
            await message.reply(f"{badge} {data['svar']}")
        except requests.RequestException as e:
            await message.reply(f"⚠️ Kunde inte nå Game Voice Helper-servern: {e}")


client.run(TOKEN)
