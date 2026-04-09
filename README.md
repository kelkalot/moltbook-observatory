# 🔭 Moltbook Observatory

**Passive monitoring and analytics dashboard for [Moltbook](https://moltbook.com)** — the social network for AI agents.

The Observatory silently watches Moltbook, collecting posts, tracking agents, and analyzing trends over time. The longer it runs, the richer your dataset becomes.  

---  

🔥📄 **Report of first patch of data collected:** [RISK ASSESSMENT REPORT Moltbook Platform & Moltbot Ecosystem](https://zenodo.org/records/18444900)

🚀🌐 **Live Running Instance:** [moltbook-observatory.sushant.info.np](https://moltbook-observatory.sushant.info.np)

🧠📊 **Dataset Snapshot on HuggingFace:** [huggingface.co/datasets/SimulaMet/moltbook-observatory-archive](https://huggingface.co/datasets/SimulaMet/moltbook-observatory-archive)


## Media Coverage

Our research has been featured in:

### Academic/Professional Publications
- **[Communications of the ACM](https://cacm.acm.org/blogcacm/openclaw-a-k-a-moltbot-is-everywhere-all-at-once-and-a-disaster-waiting-to-happen/)** - Gary Marcus: "OpenClaw (a.k.a. Moltbot) is everywhere all at once, and a disaster waiting to happen" (February 2026)

### News Outlets
- **[CBC News](https://www.cbc.ca/news/business/moltbook-explainer-debunker-9.7072555)** - "Moltbook claims to be a social network for AI bots. But humans are behind its rapid growth" (February 5, 2026)
- **[The Register](https://www.theregister.com/2026/02/03/openclaw_security_problems/)** - "OpenClaw security problems" (February 3, 2026)
- **[UnHerd](https://unherd.com/2026/02/moltbook-wont-save-you/)** - Gary Marcus: "Moltbook won't save you" (February 4, 2026)
- **[Business Insider](https://www.businessinsider.com/gary-marcus-moltbook-openclaw-security-concerns-2026-2)** - "AI researcher Gary Marcus sounds off on Moltbook and OpenClaw's viral moment" (February 6, 2026)

### Academic Citations
- **[ArXiv preprint 2602.02625](https://arxiv.org/html/2602.02625)** - "OpenClaw Agents on Moltbook: Risky Instruction Sharing and Norm Enforcement in an Agent-Only Social Network" - Uses Moltbook Observatory Archive as primary dataset (February 2026)

## How It Works

The Observatory operates as a **background data collector** that continuously polls the Moltbook API:

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Moltbook API  │────▶│    Poller Jobs   │────▶│  SQLite Database│
└─────────────────┘     └──────────────────┘     └─────────────────┘
                               │
                               ▼
                        ┌──────────────────┐
                        │   Web Dashboard  │
                        │   + REST API     │
                        └──────────────────┘
```

### Background Polling Schedule

| Job | Frequency | What It Collects |
|-----|-----------|------------------|
| **Posts** | Every 2 minutes | New posts from all submolts (50 per poll) |
| **Submolts** | Every hour | All communities, subscriber counts |
| **Agent Profiles** | Every 15 minutes | Karma, followers, descriptions |
| **Trends** | Every 10 minutes | Word frequency analysis |
| **Snapshots** | Every hour | Platform-wide metrics (for time-series) |

### Data Accumulation Over Time

The database grows continuously as new content is discovered:

| Running Time | Expected Posts | Expected Agents |
|--------------|----------------|-----------------|
| 1 hour | ~1,500 | ~100+ |
| 1 day | ~36,000 | All active agents |
| 1 week | ~252,000 | Complete agent history |
| 1 month | ~1,000,000+ | Full platform archive |

**Key insight**: Posts are fetched in reverse chronological order, so new posts are captured as they appear. Over time, you build a complete historical archive of Moltbook activity.

---

## Features

- **Live Feed** — Real-time stream of posts from the Moltbook ecosystem
- **Agent Directory** — Browse all discovered AI agents with karma, followers, descriptions
- **Submolt Browser** — All 100+ communities on Moltbook
- **Trend Analysis** — Word frequency, trending topics, and emerging themes
- **Sentiment Analysis** — Platform-wide mood using TextBlob polarity scoring
- **Analytics Dashboard** — Top posters leaderboard, activity heatmap, most active submolts
- **Hourly Snapshots** — Time-series data for historical analysis
- **Data Export** — Download everything as CSV or raw SQLite database
- **RESTful API** — Programmatic access for research and integrations

---

## Quick Start

### Prerequisites

- Python 3.11+
- A Moltbook API key (register an observer agent at [moltbook.com](https://moltbook.com))

### Installation

```bash
# Clone and enter directory
git clone https://github.com/kelkalot/moltbook-observatory.git
cd moltbook-observatory

# Install dependencies (or use pip install directly)
pip install fastapi uvicorn httpx jinja2 textblob apscheduler aiosqlite python-dotenv

# Configure your API key
cp .env.example .env
# Edit .env and set MOLTBOOK_API_KEY=your_key_here
```

### Run the Observatory

```bash
uvicorn observatory.main:app --port 8000

# Open http://localhost:8000
```

On startup, the Observatory will:
1. ✅ Create the SQLite database (if it doesn't exist)
2. ✅ Fetch all submolts immediately (~100 communities)
3. ✅ Fetch the latest 50 posts
4. ✅ Start background polling jobs
5. ✅ Serve the web dashboard

**Leave it running** — the longer it runs, the more data you collect.

---

## What Gets Stored

### Agents Table
- Name, ID, description
- Karma score, follower/following counts
- Owner X handle (if claimed)
- First seen / last active timestamps

### Posts Table
- Full content (title + body)
- Author, submolt, timestamp
- Upvotes, downvotes, comment count
- URL for reference

### Submolts Table
- Name, description
- Subscriber count, post count
- Avatar/banner URLs

### Snapshots Table (Time-Series)
- Hourly platform metrics
- Total agents, posts, comments
- Average sentiment
- Top trending words

---

## API Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/feed` | Recent posts (with `?since=timestamp&limit=50`) |
| `GET /api/stats` | Current platform metrics |
| `GET /api/trends` | Trending words (with `?hours=24`) |
| `GET /api/agents` | All agents (with `?sort=karma&limit=50`) |
| `GET /api/agents/{name}` | Single agent profile + posts |
| `GET /api/submolts` | All communities |
| `GET /api/analytics/top-posters` | Agents ranked by post count |
| `GET /api/analytics/activity-by-hour` | Post activity by hour (UTC) |
| `GET /api/analytics/submolt-activity` | Submolts ranked by post activity |
| `GET /api/export/posts.csv` | Download all posts as CSV |
| `GET /api/export/agents.csv` | Download all agents as CSV |
| `GET /api/export/database.db` | Download raw SQLite database |

---

## Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `MOLTBOOK_API_KEY` | Your Moltbook API key | **Required** |
| `DATABASE_PATH` | SQLite database location | `./data/observatory.db` |
| `POLL_POSTS_INTERVAL` | Seconds between post fetches | `120` (2 min) |
| `POLL_AGENTS_INTERVAL` | Seconds between agent updates | `900` (15 min) |
| `POLL_SUBMOLTS_INTERVAL` | Seconds between submolt fetches | `3600` (1 hour) |

---

## Deployment (Long-Running)

For continuous data collection, deploy to a server:

### VPS / Cloud Server (Recommended)

**On any Ubuntu/Debian server:**

```bash
# Clone the repository
git clone https://github.com/kelkalot/moltbook-observatory.git
cd moltbook-observatory

# Install Python 3.11+ and dependencies
sudo apt update && sudo apt install python3.11 python3-pip -y
pip install fastapi uvicorn httpx jinja2 textblob apscheduler aiosqlite python-dotenv

# Configure your API key
cp .env.example .env
nano .env  # Add your MOLTBOOK_API_KEY

# Run with screen (keeps running after SSH disconnect)
screen -S observatory
uvicorn observatory.main:app --host 0.0.0.0 --port 8000
# Press Ctrl+A then D to detach

# Or use systemd for auto-restart
sudo nano /etc/systemd/system/moltbook-observatory.service
```

**Systemd service file:**
```ini
[Unit]
Description=Moltbook Observatory
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/moltbook-observatory
ExecStart=/usr/bin/python3 -m uvicorn observatory.main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable moltbook-observatory
sudo systemctl start moltbook-observatory
```

### Railway / Fly.io

1. Push to GitHub
2. Deploy from repo
3. **Add a persistent volume** at `/data` (critical for database persistence!)
4. Set `MOLTBOOK_API_KEY` env var

### Docker

```bash
docker build -t moltbook-observatory .
docker run -d \
  -p 8080:8080 \
  -e MOLTBOOK_API_KEY=your_key \
  -v observatory-data:/data \
  --restart unless-stopped \
  moltbook-observatory
```

---

## Sample Data

The `sample_data/` directory contains example exports from the observatory:

| File | Description | Records |
|------|-------------|---------|
| `posts_sample.csv` | All collected posts with content | 262 |
| `agents_sample.csv` | All discovered agents with stats | 255 |
| `submolts_sample.csv` | All communities | 100 |

These samples demonstrate the data schema and can be used for testing analysis pipelines.

---

## Use Cases

### Research
- Study AI agent behavior and communication patterns
- Track the evolution of AI-to-AI social dynamics
- Analyze sentiment trends across time

### Analytics
- Identify popular topics and emerging discussions
- Track agent growth (karma, followers)
- Compare activity across different submolts

### Archival
- Build a historical record of early AI social networks
- Export data for academic papers
- Create reproducible datasets

---

## Project Structure

```
moltbook-observatory/
├── observatory/
│   ├── main.py           # FastAPI app + lifespan
│   ├── config.py         # Environment configuration
│   ├── database/         # SQLite schema + connection
│   ├── poller/           # API client + scheduler + processors
│   ├── analyzer/         # Trends, sentiment, statistics
│   └── web/              # Routes + Jinja2 templates
├── sample_data/          # Example CSV exports
├── data/                 # SQLite database (gitignored)
├── pyproject.toml        # Dependencies
├── Dockerfile            # Container deployment
└── .env.example          # Configuration template
```

---

## Philosophy

- **No manipulation** — We observe, never post or interact
- **Pure archival** — Every post, every agent, everything
- **Research-grade** — Data should be exportable and citable
- **Time-aware** — Not just current state, but historical trends

---

## Citation

If you use Moltbook Observatory in your research, please cite:

```bibtex
@software{moltbook_observatory,
  author = {Riegler, Michael A. and Gautam, Sushant},
  title = {Moltbook Observatory: Passive Monitoring Dashboard for AI Social Networks},
  year = {2026},
  url = {https://github.com/kelkalot/moltbook-observatory},
  note = {A research tool for collecting and analyzing data from Moltbook, the social network for AI agents}
}
```

**Plain text citation:**
> Riegler, M. A., & Gautam, S. (2026). Moltbook Observatory: Passive Monitoring Dashboard for AI Social Networks. GitHub. https://github.com/kelkalot/moltbook-observatory

---

## Contributors

- [Michael A. Riegler](https://github.com/kelkalot)
- [Sushant Gautam](https://github.com/SushantGautam)

---

## License

MIT
