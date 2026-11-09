# Aloitus Codexissa

Tämä on sama Deadpan Tech Studio -MVP kuin aiempi paketti, täydennettynä Codexin tehtävänannolla. Projektin nimeä ei ole vielä päätetty; Deadpan Tech on työnimi.

## Käynnistä

1. Pura tämä ZIP esimerkiksi kansioon `C:\\Projects\\deadpan-tech-studio`.
2. Avaa kyseinen kansio Codex-työpöytäsovelluksessa tai VS Codessa Codex-laajennuksella.
3. Avaa halutessasi terminalissa Git-repo: `git init`, `git add .`, `git commit -m "Initial Deadpan Tech MVP"`.
4. Liitä Codexille alla oleva aloitusviesti. Codex lukee `AGENTS.md`-tiedoston ja tarkemman tehtävän `docs/CODEX_FIRST_TASK.md`.

## Kopioitava ensimmäinen Codex-viesti

Continue this existing Deadpan Tech Studio project. Read AGENTS.md and docs/CODEX_FIRST_TASK.md in full, inspect the codebase, and run the existing tests. Then implement Task 01 end-to-end: improve vertical video production output, introduce editable audio-aligned short-form captions, preserve existing JSON and CLI behavior, and add tests. Keep the project local-first and working without paid services. Do not touch social publishing or add a web dashboard yet. Show a concise plan before editing, then make the changes, execute the tests and a sample render, and summarize the results plus any limitations.

## Valmiina oleva pohja
- Python CLI: `studio.py`
- Sisältö JSON-muodossa: `content/001-stop-copy-pasting.json`
- Brändiohjeet: `prompts/brand_voice.md`
- Renderöinti: `studio/render.py`, `studio/graphics.py`
- Äänet: `studio/speech.py`
- Tarkistus: `studio/quality.py`
- Testit: `tests/`

## Tulevat vaiheet (ei vielä koodattavaksi)
1. Ensimmäinen oikea, tarkistettu AI-/tech-hack-video
2. Trend Scout ja oikeiden videoaiheiden lähdetutkimus
3. Ihmisen hyväksyntänäkymä ja sisällön ajastus
4. Alustojen virallisiin rajapintoihin perustuva julkaisu
5. Analytiikka, yleisön kasvun optimointi ja myöhemmät SaaS-mahdollisuudet
