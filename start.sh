#!/usr/bin/env bash
# Startar webbservern och — om DISCORD_BOT_TOKEN är satt — Discord-röstbotten.
# Idempotent: körs vid varje anslutning till codespacet (postAttachCommand)
# och startar bara det som inte redan kör, så en återanslutning eller en
# andra klient inte krockar med en server som redan lyssnar på port 8000.
# Loggar: /tmp/game-helper-server.log och /tmp/game-helper-bot.log

cd "$(dirname "$0")"

if curl -s -o /dev/null --max-time 2 http://127.0.0.1:8000/api/status; then
  echo "Servern kör redan på port 8000 (logg: /tmp/game-helper-server.log)."
else
  echo "Startar servern (logg: /tmp/game-helper-server.log)…"
  nohup uvicorn server:app --host 0.0.0.0 --port 8000 >> /tmp/game-helper-server.log 2>&1 &
fi

if [ -z "$DISCORD_BOT_TOKEN" ]; then
  echo "Ingen DISCORD_BOT_TOKEN — hoppar över röstbotten (endast webbklienten)."
elif pgrep -f "discord_voice_bot[.]py" > /dev/null; then
  echo "Röstbotten kör redan (logg: /tmp/game-helper-bot.log)."
else
  echo "Startar Discord-röstbotten (logg: /tmp/game-helper-bot.log)…"
  nohup python discord_voice_bot.py >> /tmp/game-helper-bot.log 2>&1 &
fi
