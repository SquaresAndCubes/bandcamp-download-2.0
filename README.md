# Bandcamp Download 2.0

Downloads STS9 shows from a user's Bandcamp collection into a music
folder, one folder per show, named after the show's Bandcamp URL slug
(e.g. `20261114-royal-oak-music-theatre-royal-oak-mi`).

## Two ways to use it

**Docker is optional.** Everything is done by one script, `bandcamp_download.py`, and you
can run it on its own on any machine with Python 3.8+ (macOS and Ubuntu already have it).
Nothing to install: it only uses Python's standard library.

| | Just the script | Docker |
|---|---|---|
| What you need | Python 3 | Docker |
| How it runs | When you run it | Automatically, daily or every few hours |
| Good for | Picking shows by hand, a one-off sync, fixing folder names | A server that keeps the music folder up to date unattended |
| Instructions | [Using the script on its own](#using-the-script-on-its-own) | [Running it daily with Docker](#running-it-daily-with-docker-optional) |

Quick start without Docker:

```bash
git clone https://github.com/SquaresAndCubes/bandcamp-download-2.0.git
cd bandcamp-download-2.0
cp .env.example .env                              # then set BANDCAMP_COLLECTION_URL in it
python3 bandcamp_download.py --set-identity      # log in once (see below)
python3 bandcamp_download.py --dest ~/Music/STS9  # pick shows to download
```

The Docker setup just runs `bandcamp_download.py --sync --yes` on a schedule. Want a daily
sync without Docker? A cron job does the same:

```bash
# crontab -e   (every day at 04:00)
0 4 * * * cd /path/to/bandcamp-download-2.0 && python3 bandcamp_download.py --sync --yes --dest /path/to/STS9 >> sync.log 2>&1
```

## Files

| File | What it is | Needed for |
|---|---|---|
| `bandcamp_download.py` | The downloader. | Both |
| `.env` | **Private.** Your settings: collection URL, music folder, login cookie, Docker options. Never commit or share it. | Both |
| `.env.example` | Template for `.env`. | Both |
| `identity.txt` | **Private, optional.** The login cookie on its own; used if `.env` has none. Created by `--set-identity`. | Script |
| `scheduler.py` | Runs the sync daily at `SYNC_TIME` (or every `SYNC_EVERY`) and sends notifications. | Docker |
| `Dockerfile`, `docker-compose.yml` | The container. | Docker |

## Using the script on its own

`bandcamp_download.py` runs with Python 3.8+ and needs nothing installed (standard library
only). Run `python3 bandcamp_download.py --help` for a short summary.

### Setup

Copy `.env.example` to `.env` (in the same folder as the script) and set:

- `BANDCAMP_COLLECTION_URL`: your collection page, `https://bandcamp.com/<your Bandcamp username>`.
- `BANDCAMP_SYNC_DEST`: your music folder, used by `--sync` and `--fix-names` when you don't
  pass `--dest`.

Your settings stay in `.env`, which is git-ignored, so they never end up on GitHub. You can
also skip `.env` and pass `--url` and `--dest` every time.

### Logging in

Bandcamp only gives download links to the logged-in owner of the collection, so the script
needs your Bandcamp `identity` cookie:

1. Log in at https://bandcamp.com in your browser.
2. Open DevTools → Application (Storage in Firefox) → Cookies → `https://bandcamp.com`.
3. Copy the value of the cookie named `identity`.
4. Save it with `python3 bandcamp_download.py --set-identity` (paste it; it's checked with
   Bandcamp, then saved to `identity.txt` and `.env`). Or put it in `identity.txt` yourself
   (one line, nothing else), or set `BANDCAMP_IDENTITY='<value>'` when running the script.

Listing shows works without logging in; downloading doesn't.

### Picking shows to download

```bash
python3 bandcamp_download.py --dest ~/Music/STS9
```

This lists the 10 most recent items in the collection and asks which to download. At the
prompt, enter numbers like `1`, `1,3` or `2-5`, `a` for all, Enter for the newest show, or
`q` to quit.

Each show is extracted into a folder named after the slug in its Bandcamp URL, e.g.
`https://sts9.bandcamp.com/album/20261114-royal-oak-music-theatre-royal-oak-mi` →
`<dest>/20261114-royal-oak-music-theatre-royal-oak-mi/`. Shows whose folder already exists
are skipped.

The `.zip` files are never kept: each one goes in a temp folder (`bandcamp-dl-<random>`,
in `~/Downloads` by default) that's deleted after the show, even if the download or
extraction fails. The extracted files are then copied into `--dest`, 4 at a time. That
works for any folder, local or on a network share, and is noticeably quicker on a share.

| Option | What it does |
|---|---|
| `--count N` | How many recent shows to list (default 10). |
| `--latest` | Skip the prompt and download only the newest show. |
| `--format F` | `flac` (default), `mp3-320`, `mp3-v0`, `aac-hi`, `vorbis`, `alac`, `wav` or `aiff-lossless`. |
| `--dest DIR` | Folder the show folders go in (default: current folder; with `--sync` or `--fix-names`, `BANDCAMP_SYNC_DEST` from `.env`). `--out` is another name for it. |
| `--list` | Only show the list; don't download. |
| `--dry-run` | Get the download links but don't download. With `--latest`, a quick way to check the login works. |
| `--url URL` | The Bandcamp collection, e.g. `https://bandcamp.com/your-username` (default: `BANDCAMP_COLLECTION_URL` from `.env`). |

### Syncing the whole collection

```bash
python3 bandcamp_download.py --sync
```

Scans the **whole** collection (not just the newest 20) and downloads every release that
isn't already in `--dest`. It lists what's missing and asks before downloading.

A release counts as already downloaded if a folder has its slug as the name, or, for
folders named differently (older Bandcamp names, other date formats), the same date and a
venue word in common, or a date within 3 days and at least 3 venue words in common. Night
numbers (N1 / night-2) and soundchecks must agree. Every such match is printed so you can
check it.

| Option | What it does |
|---|---|
| `--sync` | Download everything missing from `--dest`. Add `--list` to only see what's missing. |
| `--band NAMES` | Only sync these artists, comma-separated, e.g. `"STS9,David Phipps"` (default `STS9`; `all` for everything). |
| `--yes`, `-y` | Don't ask for confirmation (for scheduled runs). |
| `--allow-empty` | Allow syncing into an empty folder. Normally refused, because an empty folder usually means the wrong path, or a network share or external drive that isn't mounted, and syncing would re-download the whole collection. |

### Fixing folder names

```bash
python3 bandcamp_download.py --fix-names --list   # preview
python3 bandcamp_download.py --fix-names          # rename (asks first)
```

Renames show folders in `--dest` whose names don't match the current Bandcamp slug (for
example because Bandcamp renamed the release), using the same matching as `--sync`. It shows
every rename and asks first, flags renames where the date differs, and writes an
`undo_renames_<time>.sh` script that reverses them.

### Updating the login cookie

```bash
python3 bandcamp_download.py --set-identity
```

Asks for a new `identity` cookie without showing what you paste (it can also be piped in,
e.g. `pbpaste | ssh server '… --set-identity'`), checks with Bandcamp that it's logged in to
the collection's account, then saves it to `identity.txt` and `.env` next to the script.
Nothing is saved if the check fails.

### Settings

Each setting can go in `.env` next to the script or be set as an environment variable
(environment variables win; this is also how the Docker container configures them):

| Variable | Default | What it is |
|---|---|---|
| `BANDCAMP_IDENTITY` | contents of `identity.txt` | Login cookie. |
| `BANDCAMP_COLLECTION_URL` | none (required, or pass `--url`) | Your collection, `https://bandcamp.com/<username>`. |
| `BANDCAMP_SYNC_DEST` | none (required for `--sync` / `--fix-names`, or pass `--dest`) | Your music folder. |
| `BANDCAMP_SYNC_BAND` | `STS9` | Default `--band`, e.g. `STS9,David Phipps`. |
| `BANDCAMP_TEMP_DIR` | `~/Downloads` | Where zips are downloaded and unpacked temporarily. |
| `BANDCAMP_LOG_DIR` | the script's folder | Where `--fix-names` writes undo scripts. |

### Exit codes

`0` success · `1` error, or some shows failed · `3` not logged in (the cookie is missing,
expired, or for another account). The scheduler uses `3` to send the "cookie expired" alert.

## Running it daily with Docker (optional)

Only needed if you want the sync to run by itself on a server. The container runs
`bandcamp_download.py --sync --yes` once a day (or every `SYNC_EVERY`, e.g. every hour)
and can send you notifications.

### Deploy on Ubuntu

1. **Install Docker** (if needed):

   ```bash
   curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER   # then log out and back in
   ```

2. **Find the music folder** on the Ubuntu machine and note the path of the STS9
   folder, for example `/mnt/music/FLAC/STS9`. It can be a local folder or disk. If it's
   on a NAS, mount the share so it's there after a reboot (e.g. an `/etc/fstab` entry).

3. **Get the code onto the Ubuntu machine**, then copy over your private `.env` if you
   already have one on another computer (it isn't in the repo):

   ```bash
   git clone https://github.com/SquaresAndCubes/bandcamp-download-2.0.git ~/bandcamp_download
   ```

   ```bash
   scp /path/to/your/.env user@ubuntu-host:~/bandcamp_download/
   ```

   No `.env` yet? Copy `.env.example` to `.env` and fill it in.

4. **Edit `.env`** on the Ubuntu machine:
   - `BANDCAMP_COLLECTION_URL`: your collection, `https://bandcamp.com/<your username>`.
   - `MUSIC_DIR`: the STS9 folder from step 2.
   - `TEMP_DIR`: where zips are kept while each show downloads (default `./tmp`, inside
     this folder). Point it at a disk with a few GB free. It must exist and be owned by
     the `PUID` user, e.g. `mkdir -p /data/bandcamp-tmp`.
   - `LOGS_DIR`: where the sync log `sync.log` is kept (default `./logs`, inside this
     folder). Same rules as `TEMP_DIR`.
   - `PUID` / `PGID`: output of `id -u` and `id -g` (the user that should own the files).
   - `SYNC_TIME` / `TZ`: when to run each day. Or `SYNC_EVERY=1h` to sync every hour
     instead (also e.g. `30m`, `6h`; runs line up with the clock).

   Paths in `.env` are paths **on the Ubuntu machine**. Inside the container they always
   appear as `/music` and `/work`, so nothing else needs changing.

5. **Check it can see your collection and folder** (lists what's missing, downloads nothing):

   ```bash
   cd ~/bandcamp_download
   docker compose run --rm bandcamp-sync python /app/bandcamp_download.py --sync --list
   ```

   **Check the login cookie works on this machine** (gets the download link for the newest
   show, downloads nothing). It should print `Download URL:`; `Not logged in` means you
   need a fresh cookie (see below):

   ```bash
   docker compose run --rm bandcamp-sync python /app/bandcamp_download.py --latest --dry-run --dest /tmp
   ```

6. **Start it:**

   ```bash
   docker compose up -d --build
   ```

   It restarts by itself after reboots (`restart: unless-stopped`).

### Day to day

```bash
docker compose logs -f                      # watch what it's doing
tail -n 100 logs/sync.log                   # past syncs (kept across updates; logs/sync.log.1 is older)
docker compose run --rm bandcamp-sync python /app/bandcamp_download.py --sync --yes   # sync now
docker compose run --rm bandcamp-sync python /app/bandcamp_download.py --fix-names   # fix folder names
docker compose up -d                        # after editing .env (restart alone doesn't reload it)
git pull && docker compose up -d --build    # after updating the code
docker compose down                         # stop it
```

### Notifications (optional)

Get a push notification on your phone for every show that downloads, a "sync done"
summary after every sync (even when nothing was new), and an alert when the login
cookie expires or a sync fails:

1. Install the **ntfy** app (iPhone/Android) and subscribe to a topic with a long, random
   name, e.g. `sts9-sync-7f3k9q2m`. Anyone who knows the name can read the messages,
   so don't use something guessable.
2. In `.env`: `NOTIFY_URL=https://ntfy.sh/sts9-sync-7f3k9q2m`
   (`NOTIFY_DOWNLOADS=false` and `NOTIFY_SYNC=false` if you only want problems).
   This also works without Docker: the same `.env` line makes `bandcamp_download.py`
   send a notification for each show it downloads, however you run it.
3. Apply and send a test:

   ```bash
   docker compose up -d
   docker compose run --rm bandcamp-sync python /app/scheduler.py --test-notify
   ```

The login is checked on every scheduled run, so you hear about an expired cookie the same day.
With `SYNC_EVERY=1h` the "sync done" summary arrives every hour; set `NOTIFY_SYNC=false`
if that's too many.

## Safety checks built in

These apply whether you run the script yourself or with Docker:

- If the music folder doesn't exist, `--sync` stops (it won't create it). If it exists but
  is **empty** (e.g. a wrong path, or a network share or external drive that isn't mounted
  so you're looking at the bare mount point), `--sync` refuses to run instead of
  re-downloading the whole collection.
- `.zip` files are never kept. They're downloaded and unpacked in a temp folder, then
  copied into the music folder and deleted. Each show needs roughly 2× its size free there
  while it's processed. If the temp folder isn't writable, the script stops with a message
  saying so (instead of every show failing).
- A show that fails halfway leaves no partial folder, so it's retried next time.

With Docker, also:

- If `MUSIC_DIR` or `TEMP_DIR` doesn't exist, the container won't start (Docker won't
  create them).
- If the container is stopped mid-download, the leftovers in `TEMP_DIR` are cleaned up the
  next time it starts.

## When the login cookie expires

The script says `Not logged in` (and with Docker, the log and the notification say the
cookie expired). Bandcamp's login uses a CAPTCHA, so this can't be done automatically.
Log in at bandcamp.com in a browser, copy the `identity` cookie (DevTools → Application →
Cookies → `https://bandcamp.com` → `identity`), then, in the project folder:

```bash
python3 bandcamp_download.py --set-identity   # paste it; it's checked, then saved
```

That's all if you run the script yourself. With Docker, also restart the container so it
picks up the new cookie:

```bash
docker compose up -d
```

`--set-identity` doesn't show what you paste, refuses a cookie that isn't logged in to
your account, and only needs the Python that comes with macOS or Ubuntu. On a headless
server, copy the cookie on your computer and pipe it over SSH:
`pbpaste | ssh user@server 'cd ~/bandcamp_download && python3 bandcamp_download.py --set-identity'`.
