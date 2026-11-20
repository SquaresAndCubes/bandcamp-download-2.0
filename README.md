# Bandcamp Download 2.0

Downloads STS9 shows from a user's Bandcamp collection into a music
folder, one folder per show, named after the show's Bandcamp URL slug
(e.g. `20261114-royal-oak-music-theatre-royal-oak-mi`).

Runs on **macOS, Windows and Linux**.

## Two ways to use it

**Docker is optional.** Everything is done by one script, `bandcamp_download.py`, which
runs on its own anywhere with Python 3.8+. It only uses Python's standard library, so
there's nothing else to install.

| | Just the script | Docker |
|---|---|---|
| What you need | Python 3.8+ | Docker (Docker Desktop on macOS / Windows) |
| How it runs | When you run it (or from cron / Task Scheduler) | By itself, daily or every few hours |
| Good for | Picking shows by hand, a one-off sync, fixing folder names | A computer or server that keeps the music folder up to date unattended |
| Set up on | [macOS](#macos) · [Linux](#linux) · [Windows](#windows) | [Linux](#docker-on-linux) · [macOS](#docker-on-macos) · [Windows](#docker-on-windows) |

## Files

| File | What it is | Needed for |
|---|---|---|
| `bandcamp_download.py` | The downloader. | Both |
| `.env` | **Private.** Your settings: collection URL, music folder, login cookie, Docker options. Never commit or share it. | Both |
| `.env.example` | Template for `.env`. | Both |
| `identity.txt` | **Private, optional.** The login cookie on its own; used if `.env` has none. Created by `--set-identity`. | Script |
| `scheduler.py` | Runs the sync daily at `SYNC_TIME` (or every `SYNC_EVERY`) and sends notifications. | Docker |
| `Dockerfile`, `docker-compose.yml` | The container. | Docker |
| `docker-compose.nas.yml` | Optional: lets Docker connect to a NAS share itself. | Docker |

## Using the script on its own

### Install and set up

Each OS below ends up in the same place: the project folder with a `.env` file in it.
Then [log in](#logging-in) once and you're ready.

#### macOS

1. **Python 3.** Open Terminal and run `python3 --version`. If macOS offers to install the
   Command Line Tools, accept: they include Python 3. (Or install it from
   https://www.python.org/downloads/.)
2. **Get the code:**

   ```bash
   git clone https://github.com/SquaresAndCubes/bandcamp-download-2.0.git ~/bandcamp-download
   cd ~/bandcamp-download
   ```

   No `git`? On GitHub, click **Code → Download ZIP** and unzip it instead.
3. **Settings:**

   ```bash
   cp .env.example .env
   open -e .env      # opens it in TextEdit
   ```

   Set `BANDCAMP_COLLECTION_URL` to your collection and `BANDCAMP_SYNC_DEST` to your music
   folder, e.g. `/Volumes/music/STS9` for a NAS share mounted in Finder, or
   `/Users/<you>/Music/STS9`.
4. [Log in](#logging-in), then e.g. `python3 bandcamp_download.py --sync`.

#### Linux

1. **Python 3.** Most distributions have it (`python3 --version`). If not:
   `sudo apt install python3` (Debian / Ubuntu) or `sudo dnf install python3` (Fedora).
2. **Get the code:**

   ```bash
   git clone https://github.com/SquaresAndCubes/bandcamp-download-2.0.git ~/bandcamp-download
   cd ~/bandcamp-download
   ```

3. **Settings:**

   ```bash
   cp .env.example .env
   nano .env
   ```

   Set `BANDCAMP_COLLECTION_URL` to your collection and `BANDCAMP_SYNC_DEST` to your music
   folder, e.g. `/home/<you>/Music/STS9`, or `/mnt/music/STS9` for a NAS share mounted
   there (add it to `/etc/fstab` so it's there after a reboot).
4. [Log in](#logging-in), then e.g. `python3 bandcamp_download.py --sync`.

#### Windows

1. **Python 3.** Install it from https://www.python.org/downloads/ and tick "Add
   python.exe to PATH" in the installer. That also installs the `py` launcher:
   **on Windows, type `py` wherever this README says `python3`.**
2. **Get the code** in PowerShell or Windows Terminal:

   ```powershell
   git clone https://github.com/SquaresAndCubes/bandcamp-download-2.0.git $HOME\bandcamp-download
   cd $HOME\bandcamp-download
   ```

   No Git? On GitHub, click **Code → Download ZIP** and unzip it instead.
3. **Settings:**

   ```powershell
   copy .env.example .env
   notepad .env
   ```

   Set `BANDCAMP_COLLECTION_URL` to your collection and `BANDCAMP_SYNC_DEST` to your music
   folder. Windows paths work as they are, e.g. `D:\Music\STS9`, or a NAS share like
   `\\nas\music\FLAC\STS9`.
4. [Log in](#logging-in), then e.g. `py bandcamp_download.py --sync`. Put paths with
   spaces in quotes: `--dest "D:\My Music\STS9"`.

Other Windows differences: temp files go to your `Downloads` folder
(`%USERPROFILE%\Downloads`), and the `--fix-names` undo file is a `.cmd` file you can
double-click.

### Logging in

Bandcamp only gives download links to the logged-in owner of the collection, so the script
needs your Bandcamp `identity` cookie:

1. Log in at https://bandcamp.com in your browser.
2. Open the developer tools (Chrome / Edge: F12 → **Application** → Cookies; Firefox:
   F12 → **Storage** → Cookies; Safari: turn on Settings → Advanced → "Show features for
   web developers", then Develop → Show Web Inspector → **Storage** → Cookies) and pick
   `https://bandcamp.com`.
3. Copy the value of the cookie named `identity`.
4. Run `python3 bandcamp_download.py --set-identity` (`py …` on Windows) and paste it
   (⌘V on a Mac, Ctrl+V or right-click on Windows / Linux). Nothing shows while you paste.
   It's checked with Bandcamp, then saved to `identity.txt` and `.env`.

   Or put it in `.env` yourself as `BANDCAMP_IDENTITY='<value>'` (keep the quotes).

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
in your `Downloads` folder by default) that's deleted after the show, even if the download
or extraction fails. The extracted files are then copied into `--dest`, 4 at a time. That
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
every rename and asks first, flags renames where the date differs, and writes an undo file
that reverses them: `undo_renames_<time>.sh` (run it with `sh`), or `.cmd` on Windows.

### Syncing on a schedule without Docker

The script can run unattended with `--sync --yes`. It uses `BANDCAMP_SYNC_DEST` from
`.env`, and the computer has to be on (and awake) at that time.

**macOS:** use cron. Because cron isn't allowed into protected folders like Documents and
Downloads by default, first give it access: System Settings → Privacy & Security → Full
Disk Access → **+** → press ⌘⇧G, type `/usr/sbin/cron`, and add it. Then `crontab -e` and
add (every day at 04:00):

```bash
0 4 * * * cd ~/bandcamp-download && /usr/bin/python3 bandcamp_download.py --sync --yes >> sync.log 2>&1
```

**Linux:** `crontab -e` and add (every day at 04:00; `0 * * * *` for every hour):

```bash
0 4 * * * cd ~/bandcamp-download && python3 bandcamp_download.py --sync --yes >> sync.log 2>&1
```

**Windows:** use Task Scheduler. In PowerShell (every day at 04:00; `/sc hourly` for
every hour):

```powershell
schtasks /create /tn "Bandcamp sync" /sc daily /st 04:00 /tr "py $HOME\bandcamp-download\bandcamp_download.py --sync --yes"
```

### Updating the login cookie

```bash
python3 bandcamp_download.py --set-identity
```

Asks for a new `identity` cookie without showing what you paste, checks with Bandcamp that
it's logged in to the collection's account, then saves it to `identity.txt` and `.env` next
to the script. Nothing is saved if the check fails. It can also be piped in, e.g. from a
Mac to a server: `pbpaste | ssh user@server 'cd ~/bandcamp-download && python3 bandcamp_download.py --set-identity'`.

### Settings

Each setting can go in `.env` next to the script or be set as an environment variable
(environment variables win; this is also how the Docker container configures them):

| Variable | Default | What it is |
|---|---|---|
| `BANDCAMP_IDENTITY` | contents of `identity.txt` | Login cookie. |
| `BANDCAMP_COLLECTION_URL` | none (required, or pass `--url`) | Your collection, `https://bandcamp.com/<username>`. |
| `BANDCAMP_SYNC_DEST` | none (required for `--sync` / `--fix-names`, or pass `--dest`) | Your music folder. |
| `BANDCAMP_SYNC_BAND` | `STS9` | Default `--band`, e.g. `STS9,David Phipps`. |
| `BANDCAMP_TEMP_DIR` | your `Downloads` folder | Where zips are downloaded and unpacked temporarily. |
| `BANDCAMP_LOG_DIR` | the script's folder | Where `--fix-names` writes undo files. |
| `NOTIFY_URL` | none | ntfy topic for push notifications (see [Notifications](#notifications-optional)). |

### Exit codes

`0` success · `1` error, or some shows failed · `3` not logged in (the cookie is missing,
expired, or for another account). The scheduler uses `3` to send the "cookie expired" alert.

## Running it on a schedule with Docker (optional)

Docker runs the sync by itself, once a day (`SYNC_TIME`) or every few hours (`SYNC_EVERY`),
on a computer that's always on, and can send you notifications. The container runs
`bandcamp_download.py --sync --yes` on that schedule. The steps are the same on every OS
apart from installing Docker and the paths you use.

### What goes in `.env` for Docker

Start from `.env.example` (`cp .env.example .env`, or `copy` on Windows) and set:

| Setting | What to put |
|---|---|
| `BANDCAMP_COLLECTION_URL` | Your collection, `https://bandcamp.com/<your username>`. |
| `BANDCAMP_IDENTITY` | Your login cookie (see [Logging in](#logging-in)), in single quotes. |
| `MUSIC_DIR` | The music folder **on this computer**, e.g. `/mnt/music/STS9` (Linux), `/Volumes/music/STS9` (macOS), `D:\Music\STS9` (Windows). Or `nas`, see [Music on a NAS](#music-on-a-nas-any-os). |
| `TEMP_DIR` | Where zips go while a show downloads. Default `./tmp` (in the project folder); needs a few GB free. |
| `LOGS_DIR` | Where `sync.log` is kept. Default `./logs`. |
| `TZ` | Your time zone, e.g. `America/Denver`, `Europe/London`. |
| `SYNC_TIME` | Time of day to sync, e.g. `04:00`. |
| `SYNC_EVERY` | Or sync every `1h`, `30m`, `6h`… instead of once a day (leave empty for daily). |
| `PUID` / `PGID` | The user that should own downloaded files. Linux: `id -u` / `id -g` (usually `1000`). macOS: `id -u` / `id -g` (often `501` / `20`). Windows: leave `1000`. |
| `NOTIFY_URL` | Optional, see [Notifications](#notifications-optional). |

Inside the container, the folders always appear as `/music`, `/work` and `/logs`, so the
log says things like `Saved to: /music/<show>`; that's your `MUSIC_DIR`.

`MUSIC_DIR`, `TEMP_DIR` and `LOGS_DIR` must already exist: Docker won't create them, so a
typo or an unmounted drive stops the container instead of filling the wrong disk.

### Docker on Linux

1. **Install Docker** (Ubuntu / Debian shown; for others see https://docs.docker.com/engine/install/):

   ```bash
   sudo apt install docker.io docker-compose-v2      # or: curl -fsSL https://get.docker.com | sudo sh
   sudo usermod -aG docker $USER                     # then log out and back in
   ```

2. **Music folder:** a local folder, or a NAS share mounted on this machine (e.g. an
   `/etc/fstab` entry for `/mnt/music`, so it's there after a reboot). Or let Docker
   connect to the NAS itself: [Music on a NAS](#music-on-a-nas-any-os).
3. **Get the code and settings:**

   ```bash
   git clone https://github.com/SquaresAndCubes/bandcamp-download-2.0.git ~/bandcamp-download
   cd ~/bandcamp-download
   cp .env.example .env && nano .env      # or copy your .env from another computer with scp
   ```

4. [Check and start it](#check-and-start-it-any-os).

Docker starts at boot and brings the container back with it. If the music folder is a
network mount, you can make Docker wait for it at boot, so the container never starts
against an empty mount point:

```bash
sudo mkdir -p /etc/systemd/system/docker.service.d
printf '[Unit]\nRequiresMountsFor=/mnt/music\n' | sudo tee /etc/systemd/system/docker.service.d/wait-for-music.conf
sudo systemctl daemon-reload
```

### Docker on macOS

1. **Install Docker Desktop** from https://www.docker.com/products/docker-desktop/ and
   open it once. In its Settings → General, turn on **Start Docker Desktop when you sign
   in to your computer**.
2. **Music folder:** a local folder, or a NAS share mounted in Finder (it appears under
   `/Volumes`, e.g. `/Volumes/music/STS9`). Docker Desktop can use folders under `/Users`
   and `/Volumes` by default. To have the share mounted again after a restart, add it to
   System Settings → General → Login Items. Or let Docker connect to the NAS itself:
   [Music on a NAS](#music-on-a-nas-any-os).
3. **Get the code and settings** in Terminal:

   ```bash
   git clone https://github.com/SquaresAndCubes/bandcamp-download-2.0.git ~/bandcamp-download
   cd ~/bandcamp-download
   cp .env.example .env && open -e .env
   ```

   Set `PUID` / `PGID` to the output of `id -u` and `id -g`.
4. [Check and start it](#check-and-start-it-any-os).

The sync only runs while the Mac is awake and you're signed in (Docker Desktop runs in
your account). For a Mac that sleeps, set `SYNC_EVERY=1h` so it catches up within an hour
of waking, or set System Settings → Energy so it doesn't sleep.

### Docker on Windows

1. **Install Docker Desktop** from https://www.docker.com/products/docker-desktop/ (it uses
   WSL 2, which the installer sets up). In its Settings → General, turn on **Start Docker
   Desktop when you sign in to your computer**.
2. **Music folder:** a folder on a local drive, e.g. `D:\Music\STS9`. Docker Desktop
   **can't use mapped network drives (like `Z:`) or `\\nas\share` paths**, so for a NAS,
   let Docker connect to it itself: [Music on a NAS](#music-on-a-nas-any-os).
3. **Get the code and settings** in PowerShell:

   ```powershell
   git clone https://github.com/SquaresAndCubes/bandcamp-download-2.0.git $HOME\bandcamp-download
   cd $HOME\bandcamp-download
   copy .env.example .env
   notepad .env
   ```

   Use Windows paths as they are, e.g. `MUSIC_DIR=D:\Music\STS9`. Leave `PUID` / `PGID`
   at `1000`. No Python on this PC? Paste the cookie into `.env` yourself as
   `BANDCAMP_IDENTITY='<value>'`.
4. [Check and start it](#check-and-start-it-any-os). The commands are the same in
   PowerShell.

The sync only runs while the PC is on and you're signed in (Docker Desktop runs in your
account). `SYNC_EVERY=1h` helps catch up after the PC has been asleep.

### Music on a NAS (any OS)

Instead of mounting the share on the computer, Docker can connect to an SMB / CIFS share
itself. This is the way to use a NAS with Docker Desktop on **Windows**, and an option on
macOS and Linux:

1. Copy the template so Docker Compose picks it up automatically (the copy is git-ignored):

   ```bash
   cp docker-compose.nas.yml docker-compose.override.yml      # Windows: copy …
   ```

2. In `.env`, set `MUSIC_DIR=nas` and fill in:
   - `NAS_HOST`: the NAS's IP address (e.g. `192.168.1.10`) or a normal DNS name.
     Names ending in `.local` usually don't work inside Docker.
   - `NAS_SHARE_PATH`: the share name and the folder inside it, e.g. `music/FLAC/STS9`.
   - `NAS_USER` / `NAS_PASSWORD`: an account that can write to it. The password stays in
     your private `.env`, and can't contain a comma.
3. [Check and start it](#check-and-start-it-any-os).

If you change these settings later, remove the old connection first:
`docker compose down`, then `docker volume rm bandcamp-download_music`, then start again.

### Check and start it (any OS)

In the project folder:

1. **Check it can see your collection and music folder** (lists what's missing, downloads
   nothing):

   ```bash
   docker compose run --rm bandcamp-sync python /app/bandcamp_download.py --sync --list
   ```

2. **Check the login works** (gets the download link for the newest show, downloads
   nothing). It should print `Download URL:`; `Not logged in` means you need a fresh
   cookie:

   ```bash
   docker compose run --rm bandcamp-sync python /app/bandcamp_download.py --latest --dry-run --dest /tmp
   ```

3. **Start it:**

   ```bash
   docker compose up -d --build
   docker compose logs      # should say when the next sync is
   ```

   It restarts by itself after a crash or reboot (`restart: unless-stopped`), as long as
   Docker is running.

### Day to day

```bash
docker compose logs -f                      # watch what it's doing
tail -n 100 logs/sync.log                   # past syncs (Windows: Get-Content logs\sync.log -Tail 100)
docker compose exec bandcamp-sync python /app/bandcamp_download.py --sync      # sync now
docker compose run --rm bandcamp-sync python /app/bandcamp_download.py --fix-names   # fix folder names
docker compose up -d                        # after editing .env (restart alone doesn't reload it)
git pull && docker compose up -d --build    # after updating the code
docker compose down                         # stop it
```

`logs/sync.log` keeps every scheduled sync across updates (`logs/sync.log.1` is older);
`docker compose logs` starts over whenever the container is recreated.

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
   docker compose exec bandcamp-sync python /app/scheduler.py --test-notify
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

- If `MUSIC_DIR`, `TEMP_DIR` or `LOGS_DIR` doesn't exist, the container won't start
  (Docker won't create them).
- If the container is stopped mid-download, the leftovers in `TEMP_DIR` are cleaned up the
  next time it starts.

## When the login cookie expires

The script says `Not logged in` (and with Docker, the log and the notification say the
cookie expired). Bandcamp's login uses a CAPTCHA, so this can't be done automatically.
Get a fresh `identity` cookie from your browser (see [Logging in](#logging-in)), then in
the project folder:

```bash
python3 bandcamp_download.py --set-identity   # Windows: py …   (paste it; it's checked, then saved)
```

Or paste it into `.env` yourself as `BANDCAMP_IDENTITY='<value>'`. That's all if you run
the script yourself. With Docker, also apply it:

```bash
docker compose up -d
```

On a headless Linux server, copy the cookie on your own computer and pipe it over SSH
(from a Mac: `pbpaste | ssh user@server 'cd ~/bandcamp-download && python3 bandcamp_download.py --set-identity'`).
A cookie from any computer works on any other.
