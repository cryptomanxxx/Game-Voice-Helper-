"""Game Voice Helper — FastAPI-server.

Kärnloop:
  1. FrameGrabber hämtar senaste bildrutan från en Twitch-ström var 3:e sekund.
  2. Webbklienten (static/index.html) lyssnar på röstfrågor med push-to-talk.
  3. Frågan + senaste bildrutan (eller uppladdad skärmbild) skickas till Claude.
  4. Det korta svenska svaret läses upp i webbläsaren med text-till-tal.

Starta:  uvicorn server:app --reload
Öppna:   http://localhost:8000
"""

import base64
import binascii

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import ai
from capture import FrameGrabber

app = FastAPI(title="Game Voice Helper")
grabber = FrameGrabber()


class StreamStart(BaseModel):
    url: str


class AskRequest(BaseModel):
    fraga: str
    mode: str = "ledtrad"  # ledtrad | direkt | kontroller
    spel: str | None = None
    screenshot_b64: str | None = None  # valfri uppladdad skärmbild (ren base64 eller data-URL)
    use_stream: bool = True  # använd senaste bildrutan från Twitch om ingen uppladdning


@app.post("/api/stream/start")
def stream_start(body: StreamStart):
    missing = FrameGrabber.dependencies_ok()
    if missing:
        raise HTTPException(500, f"Saknade beroenden: {', '.join(missing)}. Installera dem och starta om.")
    try:
        grabber.start(body.url)
    except RuntimeError as e:
        raise HTTPException(502, str(e))
    return {"ok": True, "status": grabber.status()}


@app.post("/api/stream/stop")
def stream_stop():
    grabber.stop()
    return {"ok": True}


@app.get("/api/status")
def status():
    return grabber.status()


@app.get("/api/frame")
def frame():
    data = grabber.latest_frame()
    if data is None:
        raise HTTPException(404, "Ingen färsk bildruta ännu")
    return Response(content=data, media_type="image/jpeg")


@app.post("/api/ask")
def ask(body: AskRequest):
    if not body.fraga.strip():
        raise HTTPException(400, "Tom fråga")

    image: bytes | None = None
    kalla = "ingen"

    if body.screenshot_b64:
        raw = body.screenshot_b64.split(",", 1)[-1]  # tolerera data-URL-prefix
        try:
            image = base64.b64decode(raw)
            kalla = "uppladdad"
        except (binascii.Error, ValueError):
            raise HTTPException(400, "Ogiltig base64 i screenshot_b64")
    elif body.use_stream:
        image = grabber.latest_frame()
        if image is not None:
            kalla = "twitch"

    try:
        svar = ai.fraga(body.fraga, image_jpeg=image, mode=body.mode, spel=body.spel)
    except Exception as e:  # API-fel ska nå klienten som läsbart fel, inte 500-stacktrace
        raise HTTPException(502, f"AI-anropet misslyckades: {e}")

    return {"svar": svar, "bildkalla": kalla, "mode": body.mode}


@app.get("/")
def index():
    return FileResponse("static/index.html")


app.mount("/static", StaticFiles(directory="static"), name="static")
