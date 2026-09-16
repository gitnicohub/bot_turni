# Immagini e audio punitivi

Metti qui dentro i file immagine (`.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`) e i file
audio (`.opus`, `.ogg`, `.oga`, `.mp3`, `.wav`, `.m4a`) da inviare quando qualcuno
segna un turno come "❌ Non completato".

Ad ogni evento il bot ne sceglie una immagine a caso e un audio a caso da questa
cartella e li invia entrambi (vedi `utils.helpers.pick_random_punishment_image`,
`utils.helpers.pick_random_punishment_audio` e `handlers/callback_handler.py`).
L'audio viene inviato come messaggio vocale: usa il formato `.opus`/`.ogg` con
codec Opus per una resa ottimale (waveform + durata mostrate da Telegram).

Puoi cambiare il percorso della cartella impostando `PUNISHMENT_IMAGES_DIR` in `.env`.
