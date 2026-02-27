# File Fetcher

> Batch-download files and directories from a remote SFTP server — with scheduling, resume, retry, and progress display.

---

## Features

- 📋 **File-list driven** — specify remote paths in a simple text file
- ⏰ **Scheduled downloads** — optionally start at a specific date/time
- 🔄 **Resume & retry** — interrupted downloads resume automatically; failures retry with back-off
- 📊 **Progress bars** — real-time tqdm progress for every file
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

## Intelligent Search (Google ADK + Gemini)

File Fetcher supports finding media on your server using natural language. It uses a **Google ADK agent** backed by **Gemini** — the agent autonomously searches your SFTP server, fetches ratings from **OMDb (IMDb & Rotten Tomatoes)**, and semantically filters results before presenting them.

### 1. Set up Google API Key

Get a Gemini API key from the [Google AI Studio](https://aistudio.google.com/apikey) and add it to your `.env`:

```env
GOOGLE_API_KEY=your_google_api_key
```

### 2. Set up OMDb API Key

To display IMDb and Rotten Tomatoes ratings in the console, File Fetcher uses the OMDb API.
1. Get a **free API key** (1,000 requests/day limit) from [omdbapi.com](http://www.omdbapi.com/apikey.aspx).
2. Add it to your `.env` file:
   ```env
   OMDB_API_KEY=your_issued_key_here
   ```

---

## Usage

### Using the convenience script (Recommended)

The easiest way to run the program is to use the provided `run.sh` script. It automatically ensures the Python virtual environment is created, dependencies are installed, and launches the app directly.

```bash
# Make the script executable (only needed once)
chmod +x run.sh

# Immediate download
./run.sh download
```

### Manual launch

If you prefer to manage the environment manually:

```bash
# Activate your virtual environment first
source .venv/bin/activate

python -m file_fetcher download
# Or, if installed via pip install -e .:
file-fetcher download
```

### Scheduled download

1. Set `schedule.date` and `schedule.time` in `config.yaml`.
2. Launch the app — it will display a countdown and start automatically at the scheduled time.

```bash
./run.sh
```

```
╔══════════════════════════════════════╗
║        📁  File Fetcher v0.1         ║
╚══════════════════════════════════════╝

📋  3 path(s) to download
📂  Destination: /Users/you/downloads

⏳  Download scheduled for 2026-03-01 02:00. Waiting 6h 30m 15s …
```

### Intelligent Media Search

Both TV shows and Movies are fully supported. Find items on the server by describing them:

```bash
./run.sh search "find me the latest sci-fi movies from 2025 or 2026"
```

The app will:
1. Send your query to an ADK agent (Gemini).
2. The agent scans the remote server over SFTP.
3. The agent looks up IMDb and Rotten Tomatoes ratings.
4. Results are semantically filtered and you're prompted to download!

```
🤖  Sending query to ADK agent (model: gemini-2.5-flash)…

─────────────────────────────────────────────────────────────────────────────────────
 #   | Title                                    | Year  | RT    | IMDb  | Uploaded  
─────────────────────────────────────────────────────────────────────────────────────
 1   | The Secret Agent                         | 2025  | 88%   | 7.6   | 2026-02-15
 2   | Beyond the Horizon                       | 2026  | 92%   | 8.1   | 2026-02-10
─────────────────────────────────────────────────────────────────────────────────────
2 items found.

📥  Enter numbers to download (e.g. 1,3), 'all', or 'q' to quit: 1
🚀  Downloading 1 item(s)...
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
│   ├── scanner.py              # SFTP media scanner
│   ├── ratings.py              # OMDb API client
│   ├── report.py               # CLI report & download prompt
│   ├── progress.py             # tqdm progress wrapper
│   └── agent/                  # ADK agent (Gemini-backed)
│       ├── __init__.py
│       ├── agent.py            # Agent definition & runner
│       └── tools.py            # ADK tool factories
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
