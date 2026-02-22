# File Fetcher

> Batch-download files and directories from a remote SFTP server — with scheduling, resume, retry, and progress display.

---

## Features

- 📋 **File-list driven** — specify remote paths in a simple text file
- ⏰ **Scheduled downloads** — optionally start at a specific date/time
- 🔄 **Resume & retry** — interrupted downloads resume automatically; failures retry with back-off
- 📊 **Progress bars** — real-time tqdm progress for every file
- 🔐 **Password auth** — designed for servers without SSH key exchange
- 📂 **Recursive folders** — directories are downloaded recursively, preserving structure
- 🌍 **Special characters** — handles spaces, accents, and special characters in paths

---

## Prerequisites

- **Python 3.12+**
- Access to an SFTP server (hostname, port, username, password)

---

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd file_fetcher

# Create a virtual environment (recommended)
python -m venv .venv
source .venv/bin/activate     # macOS / Linux
# .venv\Scripts\activate      # Windows

# Install the package
pip install -e .
```

---

## Configuration

### 1. Server credentials & paths — `.env`

Copy the template and fill in your values:

```bash
cp .env.example .env
```

Then edit `.env`:

```env
# ── SFTP Server ──────────────────────────────────
SFTP_HOST=your.server.com
SFTP_PORT=22
SFTP_USER=your_username
SFTP_PASSWORD=your_password

# ── Paths ────────────────────────────────────────
FILE_LIST=files_to_download.txt
DOWNLOAD_DIR=./downloads
```

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SFTP_HOST` | ✅ | — | Hostname or IP of the SFTP server |
| `SFTP_PORT` | ❌ | `22` | SFTP port |
| `SFTP_USER` | ✅ | — | Username for authentication |
| `SFTP_PASSWORD` | ✅ | — | Password for authentication |
| `FILE_LIST` | ❌ | `files_to_download.txt` | Path to the file list |
| `DOWNLOAD_DIR` | ❌ | `./downloads` | Local directory for downloaded files |

### 2. File list — `files_to_download.txt`

Create a text file with one remote path per line. Both individual files and full directories are supported. Lines starting with `#` are treated as comments.

```text
# Movies
/media/Films/The Last Horizon (2026).mkv
/media/4k/Neon Shadows/

# TV Shows
/media/Séries TV/Show Name/Season 01/
```

> **Note:** Paths with spaces, accents, and special characters are fully supported — no quoting or escaping needed.

### 3. Scheduling (optional) — `config.yaml`

To delay the download until a specific date and time, edit `config.yaml`:

```yaml
schedule:
  date: "2026-03-01"
  time: "02:00"
```

Omit the `schedule` section (or leave it commented out) to start downloading immediately.

---

## Usage

### Immediate download

```bash
python -m file_fetcher
```

Or, if installed via `pip install -e .`:

```bash
file-fetcher
```

### Scheduled download

1. Set `schedule.date` and `schedule.time` in `config.yaml`.
2. Launch the app — it will display a countdown and start automatically at the scheduled time.

```bash
python -m file_fetcher
```

```
╔══════════════════════════════════════╗
║        📁  File Fetcher v0.1         ║
╚══════════════════════════════════════╝

📋  3 path(s) to download
📂  Destination: /Users/you/downloads

⏳  Download scheduled for 2026-03-01 02:00. Waiting 6h 30m 15s …
```

### Resuming interrupted downloads

If a download is interrupted (Ctrl+C, network drop, etc.), simply re-run the same command. File Fetcher will:

- **Skip** files that are already fully downloaded.
- **Resume** partially downloaded files from where they left off.
- **Retry** failed transfers automatically (up to 3 attempts with back-off).

### Example output

```
╔══════════════════════════════════════╗
║        📁  File Fetcher v0.1         ║
╚══════════════════════════════════════╝

📋  3 path(s) to download
📂  Destination: /Users/you/downloads

🔗  Connecting to your.server.com:22 …
✅  Connected.

── [1/3] /media/Films/The Last Horizon (2026).mkv
The Last Horizon (2026).mkv: 100%|██████████| 4.20G/4.20G [05:32<00:00, 12.6MB/s]
── [2/3] /media/4k/Neon Shadows/
Neon.Shadows.2160p.mkv:  100%|██████████| 8.10G/8.10G [10:15<00:00, 13.1MB/s]
── [3/3] /media/Séries TV/Show Name/Season 01/
S01E01.mkv:              100%|██████████| 1.50G/1.50G [01:55<00:00, 12.9MB/s]
S01E02.mkv:              100%|██████████| 1.48G/1.48G [01:52<00:00, 13.0MB/s]

──────────────────────────────────────────────────
📊  Summary: 4 items processed
    ✅  4 downloaded
    ⏭️   0 skipped (already complete)
    ❌  0 failed

🔌  Disconnected.
```

---

## Project Structure

```
file_fetcher/
├── README.md
├── pyproject.toml              # Dependencies & entry point
├── config.yaml                 # Schedule configuration
├── .env                        # Credentials (gitignored)
├── .env.example                # Template for .env
├── files_to_download.txt       # Remote paths to download
│
├── src/file_fetcher/
│   ├── __init__.py
│   ├── __main__.py             # CLI entry point
│   ├── config.py               # Configuration loader
│   ├── scheduler.py            # Wait-until-target-time
│   ├── sftp_client.py          # SFTP download engine
│   └── progress.py             # tqdm progress wrapper
│
└── tests/                      # Unit tests
```

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `❌ Missing required environment variable: SFTP_HOST` | Copy `.env.example` to `.env` and fill in your server details. |
| `Connection refused` | Verify the host, port, and that the SFTP service is running. |
| `Authentication failed` | Double-check `SFTP_USER` and `SFTP_PASSWORD` in `.env`. |
| `Path not found on server` | Ensure the paths in `files_to_download.txt` are correct absolute paths. |
| Filenames with special characters fail | This shouldn't happen — if it does, please open an issue. |

---

## License

See [LICENSE](LICENSE).
