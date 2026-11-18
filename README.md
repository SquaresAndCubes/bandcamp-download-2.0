# Bandcamp STS9 sync

Downloads STS9 shows from the `squaresandcubes` Bandcamp collection into a music
folder, one folder per show, named after the show's Bandcamp URL slug
(e.g. `20261114-royal-oak-music-theatre-royal-oak-mi`).

The Docker container runs `bandcamp_latest.py --sync --yes` once a day: it scans
the whole collection and downloads every STS9 release that isn't already in the
music folder.

## Files

| File | What it is |
|---|---|
| `bandcamp_latest.py` | The downloader. Also runs on its own (see `--help`). |
| `scheduler.py` | Container main process: runs the sync daily at `SYNC_TIME`. |
| `Dockerfile`, `docker-compose.yml` | The container. |
| `.env` | **Private.** Your Bandcamp login cookie and settings. Never commit or share it. |
| `.env.example` | Template for `.env`. |
| `identity.txt` | **Private.** The login cookie for running the script directly on the Mac. |

## Deploy on Ubuntu

1. **Install Docker** (if needed):

   ```bash
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER   # then log out and back in
   ```

2. **Mount the music share** on the Ubuntu machine so it's there after a reboot
   (e.g. an `/etc/fstab` entry for your NAS). Note the path of the STS9 folder,
   for example `/mnt/music/FLAC/STS9`.

3. **Copy this folder** to the Ubuntu machine, including the hidden `.env`:

   ```bash
   scp -r ~/Documents/bandcamp_download user@ubuntu-host:~/
   ```

4. **Edit `.env`** on the Ubuntu machine:
   - `MUSIC_DIR`: the STS9 folder from step 2.
   - `TEMP_DIR`: where zips are kept while each show downloads (default `./tmp`, inside
     this folder). Point it at a disk with a few GB free. It must exist and be owned by
     the `PUID` user, e.g. `mkdir -p /data/bandcamp-tmp`.
   - `PUID` / `PGID`: output of `id -u` and `id -g` (the user that should own the files).
   - `SYNC_TIME` / `TZ`: when to run each day.

   Paths in `.env` are paths **on the Ubuntu machine**. Inside the container they always
   appear as `/music` and `/work`, so nothing else needs changing.

5. **Check it can see your collection and folder** (lists what's missing, downloads nothing):

   ```bash
   cd ~/bandcamp_download
   docker compose run --rm bandcamp-sync python /app/bandcamp_latest.py --sync --list
   ```

   **Check the login cookie works on this machine** (gets the download link for the newest
   show, downloads nothing). It should print `Download URL:`; `Not logged in` means you
   need a fresh cookie (see below):

   ```bash
   docker compose run --rm bandcamp-sync python /app/bandcamp_latest.py --latest --dry-run --dest /tmp
   ```

6. **Start it:**

   ```bash
   docker compose up -d --build
   ```

   It restarts by itself after reboots (`restart: unless-stopped`).

## Day to day

```bash
docker compose logs -f                      # watch what it's doing
docker compose run --rm bandcamp-sync python /app/bandcamp_latest.py --sync --yes   # sync now
docker compose run --rm bandcamp-sync python /app/bandcamp_latest.py --fix-names   # fix folder names
docker compose restart                      # after editing .env
docker compose up -d --build                # after changing the code
docker compose down                         # stop it
```

## Safety checks built in

- If `MUSIC_DIR` doesn't exist, the container won't start (Docker won't create it).
- If the folder exists but is **empty** (e.g. the share isn't mounted and you're looking
  at the bare mount point), the sync refuses to run instead of re-downloading the whole
  collection.
- `.zip` files are never kept. They're downloaded and unpacked in `TEMP_DIR`, then copied
  into the music folder and deleted. Each show needs roughly 2× its size free there while
  it's processed. If the container is stopped mid-download, the leftovers are cleaned up
  the next time it starts.
- If `TEMP_DIR` doesn't exist the container won't start, and if it isn't writable the
  sync stops with a message saying so (instead of every show failing).
- A show that fails halfway leaves no partial folder, so it's retried on the next run.

## Notifications (optional)

Get a push notification on your phone when the login cookie expires, when a sync fails,
or when new shows are downloaded:

1. Install the **ntfy** app (iPhone/Android) and subscribe to a topic with a long, random
   name, e.g. `sts9-sync-7f3k9q2m`. Anyone who knows the name can read the messages,
   so don't use something guessable.
2. In `.env`: `NOTIFY_URL=https://ntfy.sh/sts9-sync-7f3k9q2m`
   (and `NOTIFY_DOWNLOADS=false` if you only want problems).
3. Apply and send a test:

   ```bash
   docker compose up -d
   docker compose run --rm bandcamp-sync python /app/scheduler.py --test-notify
   ```

The login is checked on every daily run, so you hear about an expired cookie the same day.

## When the login cookie expires

The log (and the notification) will say the cookie expired. Bandcamp's login uses a
CAPTCHA, so this can't be done automatically. Log in at bandcamp.com in a browser, copy the
`identity` cookie (DevTools → Application → Cookies → `https://bandcamp.com` → `identity`),
then on the server:

```bash
cd ~/bandcamp_download
python3 bandcamp_latest.py --set-identity   # paste it; it's checked, then saved to .env
docker compose up -d                        # restart the container with the new cookie
```

`--set-identity` doesn't show what you paste, refuses a cookie that isn't logged in to
your account, and only needs the Python that comes with Ubuntu.
