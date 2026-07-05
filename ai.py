"""AI-lagret: skickar bildruta + fråga till Claude och får ett kort svenskt svar.

Tre lägen:
  - ledtrad:    knuffar spelaren i rätt riktning utan att avslöja lösningen
  - direkt:     rakt svar på hur man kommer vidare
  - kontroller: förklarar knappar, mekanik och gränssnitt

Svaren hålls korta (2–4 meningar) eftersom de läses upp med text-till-tal.
"""

import base64
import os

import anthropic

MODEL = os.environ.get("GAME_HELPER_MODEL", "claude-opus-4-8")
SPEL = os.environ.get("GAME_HELPER_SPEL", "Red Matter 2")
PLATTFORM = os.environ.get("GAME_HELPER_PLATTFORM", "PS5 med PSVR2")

client = anthropic.Anthropic()

_BAS = (
    "Du är en vänlig spelkompanjon som hjälper en spelare som just nu spelar "
    "{spel} på {plattform}. Spelaren pratar med dig via röst medan hen spelar, "
    "och ditt svar läses upp högt med text-till-tal.\n\n"
    "Regler:\n"
    "- Svara ALLTID på svenska.\n"
    "- Håll svaret kort: 2–4 meningar. Inga listor, ingen markdown, ingen kod.\n"
    "- Om en skärmbild bifogas: utgå från vad som faktiskt syns på den.\n"
    "- Om ingen skärmbild finns eller den är otydlig: säg det kort och svara "
    "utifrån din kunskap om spelet.\n"
    "- Spoila aldrig handlingen längre fram än där spelaren befinner sig, "
    "om spelaren inte uttryckligen ber om det.\n"
    "- Hitta inte på detaljer du är osäker på — säg hellre att du är osäker."
)

_LAGEN = {
    "ledtrad": (
        "LÄGE: LEDTRÅD. Ge en knuff i rätt riktning utan att avslöja lösningen. "
        "Ställ gärna en ledande fråga eller peka på något i miljön som spelaren "
        "bör titta närmare på. Avslöja INTE hela lösningen."
    ),
    "direkt": (
        "LÄGE: DIREKT SVAR. Spelaren vill komma vidare nu. Ge det konkreta svaret "
        "eller lösningen rakt på sak, steg för steg om det behövs, men fortfarande "
        "kort och talbart."
    ),
    "kontroller": (
        "LÄGE: KONTROLLER & MEKANIK. Fokusera på hur spelet styrs: knappar, "
        "handkontroller, grepp, verktyg, menyer och spelmekanik på spelarens "
        "plattform. Förklara pedagogiskt för någon som är ny i spelet."
    ),
}


def fraga(
    question: str,
    image_jpeg: bytes | None = None,
    mode: str = "ledtrad",
    spel: str | None = None,
) -> str:
    system = _BAS.format(spel=spel or SPEL, plattform=PLATTFORM)
    system += "\n\n" + _LAGEN.get(mode, _LAGEN["ledtrad"])

    content: list[dict] = []
    if image_jpeg:
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/jpeg",
                    "data": base64.standard_b64encode(image_jpeg).decode("utf-8"),
                },
            }
        )
        content.append(
            {
                "type": "text",
                "text": (
                    "Skärmbilden ovan är från min pågående spelsession just nu. "
                    f"Min fråga: {question}"
                ),
            }
        )
    else:
        content.append(
            {
                "type": "text",
                "text": f"(Ingen skärmbild tillgänglig just nu.) Min fråga: {question}",
            }
        )

    response = client.messages.create(
        model=MODEL,
        max_tokens=600,
        system=system,
        messages=[{"role": "user", "content": content}],
    )

    if response.stop_reason == "refusal":
        return "Jag kan tyvärr inte svara på den frågan. Prova att formulera om den."

    text = next((b.text for b in response.content if b.type == "text"), "")
    return text.strip() or "Jag fick inget svar den här gången — prova igen."
