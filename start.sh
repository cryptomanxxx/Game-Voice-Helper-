#!/usr/bin/env bash
# Startar webbservern och — om DISCORD_BOT_TOKEN är satt — Discord-röstbotten.
# Används av Codespaces (postAttachCommand) men funkar lika bra lokalt.
set -m

uvicorn server:app --host 0.0.0.0 --port 8000 &

if [ -n "$DISCORD_BOT_TOKEN" ]; then
  echo "DISCORD_BOT_TOKEN hittad — startar röstbotten…"
  python discord_voice_bot.py &
else
  echo "Ingen DISCORD_BOT_TOKEN — hoppar över röstbotten (endast webbklienten)."
fi

wait
