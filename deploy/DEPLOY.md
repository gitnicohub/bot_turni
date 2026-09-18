# Deploy su Google Cloud (VM Always Free)

Guida per far girare il bot 24/7 gratis su una VM `e2-micro` del piano
Always Free di Google Cloud. Il bot resta invariato: stesso `main.py`
con polling e scheduler in-process, gestito da systemd così riparte da
solo in caso di crash o riavvio della VM.

Requisiti: un account Google con [gcloud CLI](https://cloud.google.com/sdk/docs/install)
installato (o usa direttamente Cloud Shell dal browser, non serve installare nulla).

## 1. Creare la VM gratuita

L'Always Free tier copre **una** istanza `e2-micro` nelle region
`us-west1`, `us-central1` o `us-east1` — usa una di queste per restare
nel piano gratuito.

```bash
gcloud compute instances create bot-turni-vm \
  --zone=us-central1-a \
  --machine-type=e2-micro \
  --image-family=debian-12 \
  --image-project=debian-cloud \
  --boot-disk-size=30GB \
  --boot-disk-type=pd-standard
```

## 2. Connettersi via SSH

```bash
gcloud compute ssh bot-turni-vm --zone=us-central1-a
```

## 3. Creare un utente dedicato per il bot

Eseguire il bot con un utente non-root è buona norma:

```bash
sudo adduser --disabled-password --gecos "" botturni
sudo su - botturni
```

Da qui in poi i comandi vanno eseguiti come utente `botturni`.

## 4. Clonare il repo e lanciare il setup

```bash
git clone https://github.com/gitnicohub/bot_turni.git
cd bot_turni
bash deploy/setup_vm.sh
```

Lo script (`deploy/setup_vm.sh`):
- installa Python/venv
- crea il virtual environment e installa `requirements.txt`
- copia `.env.example` in `.env` (da completare col token del bot)
- installa il servizio systemd `bot-turni.service`

## 5. Configurare il token

```bash
nano .env
```

Inserisci il `TELEGRAM_BOT_TOKEN` ottenuto da [@BotFather](https://t.me/BotFather)
e gli altri valori (vedi `.env.example`). Salva ed esci.

## 6. Avviare il bot

Da un utente con `sudo` (es. torna al tuo utente principale con `exit`,
oppure usa `sudo` se `botturni` ne ha i permessi):

```bash
sudo systemctl start bot-turni
sudo systemctl status bot-turni
```

Log in tempo reale:

```bash
journalctl -u bot-turni -f
```

Il servizio è già abilitato all'avvio automatico (`systemctl enable`,
fatto dallo script), quindi sopravvive a riavvii della VM.

## Aggiornare il bot dopo una modifica al codice

```bash
sudo su - botturni
cd bot_turni
git pull
./venv/bin/pip install -r requirements.txt   # solo se sono cambiate le dipendenze
exit
sudo systemctl restart bot-turni
```

## Note

- **Nessuna porta da aprire**: il bot fa polling verso Telegram (connessioni
  in uscita), non serve configurare firewall o IP statico.
- **Database**: `bot_turni.db` resta un file SQLite locale sulla VM. Il
  disco da 30GB del piano free è ampiamente sufficiente; se vuoi backup
  periodici, un semplice cron con `cp bot_turni.db backup/` basta.
- **Costi**: `e2-micro` + 30GB `pd-standard` in una delle tre region indicate
  rientrano nell'Always Free tier. Oltre quei limiti (es. altre VM, disco
  più grande, region diversa) si inizia a pagare — controlla la
  [pagina Always Free](https://cloud.google.com/free/docs/free-cloud-features#compute)
  per i limiti aggiornati.
