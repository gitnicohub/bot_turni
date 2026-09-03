# Immagini punitive

Metti qui dentro i file immagine (`.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`) da mostrare
quando qualcuno segna un turno come "❌ Non completato".

Ad ogni evento il bot ne sceglie una a caso da questa cartella (vedi
`utils.helpers.pick_random_punishment_image` e `handlers/callback_handler.py`).

Puoi cambiare il percorso della cartella impostando `PUNISHMENT_IMAGES_DIR` in `.env`.
