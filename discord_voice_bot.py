"""Discord-röstbot — prata med spelkompanjonen helt via PSVR2-headsetet.

Flöde:
  1. Länka ditt Discord-konto till PS5:n och gå med i en röstkanal
     (starta samtalet i Discord-appen på mobilen → "Överför till PlayStation").
  2. Boten ansluter automatiskt till kanalen när du går med.
  3. Säg väckningsfrasen ("hej kompis") följt av din fråga i ett svep.
  4. Boten transkriberar ditt tal (faster-whisper, lokalt), frågar servern
     (/api/ask — som ser din Twitch-ström) och läser upp svaret i kanalen
     (edge-tts, svensk röst) — direkt i dina hörlurar.

Servern (uvicorn server:app) måste vara igång samtidigt.

Miljövariabler:
  DISCORD_BOT_TOKEN          obligatorisk — bot-token från discord.com/developers
  GAME_HELPER_SERVER         standard http://localhost:8000
  GAME_HELPER_VAKNINGSFRAS   standard "hej kompis"
  GAME_HELPER_LYSSNA_ALLT    "1" = varje mening är en fråga (ingen fras krävs)
  GAME_HELPER_WHISPER        tiny|base|small|medium — standard "small"
  GAME_HELPER_TTS_ROST       standard "sv-SE-SofieNeural" (alt. sv-SE-MattiasNeural)
"""

import asyncio
import os
import re
import tempfile
import time

import discord
import edge_tts
import numpy as np
import requests
from discord.ext import commands, voice_recv

TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")
SERVER = os.environ.get("GAME_HELPER_SERVER", "http://localhost:8000")
VAKNINGSFRAS = os.environ.get("GAME_HELPER_VAKNINGSFRAS", "hej kompis")
LYSSNA_ALLT = os.environ.get("GAME_HELPER_LYSSNA_ALLT") == "1"
WHISPER_MODELL = os.environ.get("GAME_HELPER_WHISPER", "small")
TTS_ROST = os.environ.get("GAME_HELPER_TTS_ROST", "sv-SE-SofieNeural")

# Discord levererar 48 kHz 16-bit stereo → 192 000 byte per sekund
BYTE_PER_S = 48000 * 2 * 2
TYST_S = 0.9        # så här länge ska det vara tyst innan en mening anses klar
MIN_LJUD_S = 0.4    # kortare yttranden ignoreras (host, klick, knapptryck)
MAX_LJUD_S = 30     # skydd mot obegränsad buffert

_whisper = None


def whisper():
    global _whisper
    if _whisper is None:
        from faster_whisper import WhisperModel
        print(f"Laddar whisper-{WHISPER_MODELL} (modellen laddas ner första gången)…")
        _whisper = WhisperModel(WHISPER_MODELL, device="cpu", compute_type="int8")
    return _whisper


def normalisera(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[.,!?;:]", " ", s.lower())).strip()


def pcm_till_float32(pcm: bytes) -> np.ndarray:
    """48 kHz 16-bit stereo-PCM → 16 kHz mono float32 (formatet whisper vill ha)."""
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
    x = x[: len(x) // 2 * 2]
    mono = x.reshape(-1, 2).mean(axis=1)
    return mono[::3].copy()  # 48000 / 3 = 16000


def extrahera_fraga(text: str):
    """Returnerar (fraga, mode) om texten innehåller väckningsfrasen, annars None."""
    t = normalisera(text)
    if LYSSNA_ALLT:
        fraga = t
    else:
        fras = normalisera(VAKNINGSFRAS) or "hej kompis"
        i = t.find(fras)
        if i == -1:
            return None
        fraga = t[i + len(fras):].strip()
    if len(fraga) < 3:
        return None
    mode = "ledtrad"
    for prefix, m in (("direkt svar", "direkt"), ("kontroller", "kontroller")):
        if fraga.startswith(prefix):
            rest = fraga[len(prefix):].strip()
            if rest:
                fraga, mode = rest, m
            break
    return fraga, mode


def transkribera(pcm: bytes) -> str:
    ljud = pcm_till_float32(pcm)
    segment, _ = whisper().transcribe(ljud, language="sv", beam_size=1, vad_filter=True)
    return " ".join(s.text.strip() for s in segment).strip()


def fraga_servern(fraga: str, mode: str) -> str:
    try:
        r = requests.post(
            f"{SERVER}/api/ask",
            json={"fraga": fraga, "mode": mode, "use_stream": True},
            timeout=90,
        )
        r.raise_for_status()
        return r.json()["svar"]
    except Exception as e:
        print(f"Serverfel: {e}")
        return "Något gick fel när jag frågade servern. Kolla att den är igång."


# ---------- Discord-bot ----------

intents = discord.Intents.default()
intents.message_content = True  # för !join / !lamna som reservväg
intents.voice_states = True
bot = commands.Bot(command_prefix="!", intents=intents)

upptagen = asyncio.Lock()   # en fråga i taget
buffertar = {}              # user_id -> [bytearray, tid för senaste paketet]


def ta_emot(user, data):
    """Körs i voice-tråden för varje 20 ms ljudpaket från en användare."""
    if user is None or getattr(user, "bot", False):
        return
    buf = buffertar.setdefault(user.id, [bytearray(), 0.0])
    if len(buf[0]) < MAX_LJUD_S * BYTE_PER_S:
        buf[0] += data.pcm
    buf[1] = time.monotonic()


async def saga(vc, text: str):
    """Läs upp text i röstkanalen (edge-tts → mp3 → ffmpeg)."""
    if not text or not vc.is_connected():
        return
    fil = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False).name
    try:
        try:
            await edge_tts.Communicate(text, TTS_ROST).save(fil)
        except Exception as e:
            print(f"TTS-fel (edge-tts): {e} — svaret i text: {text}")
            return
        if vc.is_playing():
            vc.stop_playing()  # inte vc.stop() — den dödar även mikrofonmottagningen
        loop = asyncio.get_running_loop()
        klar = asyncio.Event()
        vc.play(discord.FFmpegPCMAudio(fil), after=lambda _: loop.call_soon_threadsafe(klar.set))
        await klar.wait()
    finally:
        try:
            os.unlink(fil)
        except OSError:
            pass


async def hantera_yttrande(vc, pcm: bytes):
    if upptagen.locked():
        return  # en fråga hanteras redan — släpp denna
    async with upptagen:
        loop = asyncio.get_running_loop()
        text = await loop.run_in_executor(None, transkribera, pcm)
        if text:
            print(f"Hörde: {text}")
        utdrag = extrahera_fraga(text or "")
        if not utdrag:
            return
        fraga, mode = utdrag
        print(f"Fråga ({mode}): {fraga}")
        await saga(vc, "Jag kollar!")
        svar = await loop.run_in_executor(None, fraga_servern, fraga, mode)
        print(f"Svar: {svar}")
        await saga(vc, svar)


async def lyssnar_loop(vc):
    """Flushar en användares buffert när det varit tyst tillräckligt länge."""
    while vc.is_connected():
        await asyncio.sleep(0.25)
        nu = time.monotonic()
        for uid, (data, senast) in list(buffertar.items()):
            if senast and nu - senast > TYST_S:
                buffertar.pop(uid, None)
                if len(data) >= MIN_LJUD_S * BYTE_PER_S:
                    asyncio.create_task(hantera_yttrande(vc, bytes(data)))
    buffertar.clear()


async def anslut(kanal) -> None:
    vc = await kanal.connect(cls=voice_recv.VoiceRecvClient)
    vc.listen(voice_recv.BasicSink(ta_emot))
    asyncio.create_task(lyssnar_loop(vc))
    await saga(vc, f"Hej! Säg {VAKNINGSFRAS} följt av din fråga, så hjälper jag dig.")


@bot.event
async def on_ready():
    print(f"Inloggad som {bot.user} — går med i röstkanalen så fort du gör det.")
    # Ladda whisper direkt så första frågan inte behöver vänta på modellen
    await asyncio.get_running_loop().run_in_executor(None, whisper)
    print("Taligenkänningen är redo.")


@bot.event
async def on_voice_state_update(member, before, after):
    if member.bot:
        return
    vc = member.guild.voice_client
    if after.channel is not None:
        # En människa gick med i (eller bytte till) en röstkanal — följ efter
        if vc is None:
            await anslut(after.channel)
        elif vc.channel != after.channel:
            await vc.disconnect()
            await anslut(after.channel)
    elif before.channel is not None and vc is not None and vc.channel == before.channel:
        # Lämna när det bara är bottar kvar
        if all(m.bot for m in before.channel.members):
            await vc.disconnect()


@bot.command(name="join")
async def join(ctx):
    """Reservväg: !join i en textkanal medan du sitter i en röstkanal."""
    if ctx.author.voice is None or ctx.author.voice.channel is None:
        await ctx.send("Gå med i en röstkanal först.")
        return
    if ctx.guild.voice_client is not None:
        await ctx.guild.voice_client.disconnect()
    await anslut(ctx.author.voice.channel)


@bot.command(name="lamna")
async def lamna(ctx):
    if ctx.guild.voice_client is not None:
        await ctx.guild.voice_client.disconnect()
        await ctx.send("Har lämnat röstkanalen.")


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("Sätt DISCORD_BOT_TOKEN (bot-token från discord.com/developers).")
    bot.run(TOKEN)
