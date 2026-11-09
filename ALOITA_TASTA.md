# Projektin startti — suomeksi

Tämä on **toimiva tekninen MVP**, ei vielä julkaisuvalmis TikTok-/Shorts-videotehdas. Brändinimi **DEADPAN TECH on vain työnimi**.

## Mitä tässä versiossa voi jo tehdä?

- Tuottaa AI:lla englanninkielisiä käsikirjoitusluonnoksia, kun Gemini-avain on asetettu.
- Muokata käsikirjoituksia JSON-tiedostoina.
- Tarkastaa perustason sisältö- ja hyväksyntäsääntöjä.
- Tuottaa koneäänen (eSpeak testiin, Piper paikallisesti tai edge-tts erillisasennuksella).
- Renderöidä 9:16 H.264/AAC -videon. Aidot ruutukaappausvideot ja kuvat voi liittää sceneihin.
- Säilyttää hyväksyntäportin: videoita EI julkaista automaattisesti.

## Kolme komentoa alkuun (PowerShell)

Asenna Python (3.11+), FFmpeg ja riippuvuudet README:n ohjeilla. Sitten:

```powershell
python studio.py review content/001-stop-copy-pasting.json
python studio.py render content/001-stop-copy-pasting.json
# Kun edge-tts on asennettu ja haluat kokeilla parempaa englantiääntä:
python studio.py build content/001-stop-copy-pasting.json --engine edge
```

Renderöity video syntyy `output/`-kansioon. Demo sisältää tarkoituksella paikkamerkkigrafiikkaa; se todistaa koodin toiminnan, ei sisällön lopullista laatua.

## Ensimmäinen oikea tuotantotesti

1. Valitse yksi yksinkertainen, aidosti testattava AI/tech hack.
2. Nauhoita 10–20 sekuntia itse työkalun käyttöliittymästä ilman henkilötietoja.
3. Lisää tallenne videon JSON-tiedoston `scenes[].asset`-kenttään, esimerkiksi `assets/my-demo.mp4`.
4. Generoi tai kirjoita lyhyt 30 sekunnin käsikirjoitus ja lisää kertojaääni.
5. Renderöi, katso video itse ja korjaa huumori, faktat, rytmitys ja grafiikat.

## Mitä tehdään seuraavaksi?

Seuraava järkevä kehitysvaihe on **yksi julkaisuvalmis 30–40 sekunnin video** laadukkaalla äänellä, oikealla screencastilla ja dynaamisilla tekstityksillä. Sen jälkeen kannattaa tehdä trendien haku, paremmat editointitemplatet, hyväksyntänäkymä ja vasta viimeisenä automaattinen monikanavajulkaisu.

Halpa, luotettava ja omaperäinen sisältöputki on tärkeämpi kuin 100 automaattisesti generoituvaa videota, joita kukaan ei katso.
