# cosmosphere

Personal agentic astro-research tool. Every day, fetches new papers from arxiv `astro-ph.HE`, scores them against a personal taste profile via LLM, and writes a markdown digest of the top picks.

## Commands

```bash
# daily digest
uv run cosmosphere run

# plain-language explanations (amateur mode)
uv run cosmosphere run --mode amateur

# deep-dive a single paper
uv run cosmosphere explain 2504.12345 --mode amateur

# blog post from today's digest
uv run cosmosphere post --mode amateur --lang pl

# weekly roundup
uv run cosmosphere weekly

# with NASA APOD prepended + desktop notification for 9/10 papers
uv run cosmosphere run --apod --notify

# publish digest to Quartz blog via git push
uv run cosmosphere run --publish
```

Output: `data/digests/YYYY-MM-DD.md`

## Quick start

```bash
uv sync
cp .env.example .env
# edit .env — add at least one API key

uv run cosmosphere run --provider anthropic
```

## Providers

| Provider | Flag | Key needed |
|---|---|---|
| Anthropic (default) | `--provider anthropic` | `ANTHROPIC_API_KEY` |
| OpenAI | `--provider openai` | `OPENAI_API_KEY` |
| Gemini | `--provider gemini` | `GEMINI_API_KEY` |
| Claude Code CLI | `--provider claude-code` | none (uses local `claude`) |

Install optional providers:
```bash
uv sync --extra openai
uv sync --extra gemini
uv sync --extra all-providers
```

## Modes

| Mode | Style | Default lang |
|---|---|---|
| `--mode expert` (default) | technical, concise, 1-2 sentences | English |
| `--mode amateur` | plain language, analogies, 3-5 sentences | English |

Override language: `--lang pl` or `--lang en`

## Why

I read arxiv manually when I have time — rarely enough. Built an agent that skims 30 abstracts, finds 3 worth reading, and leaves me the fun part.

Also a demo of the agentic pipeline shape I use daily: multi-source fetch → LLM synthesis → published artifact. Same structure as CI/CD, same structure as an automated ops report.

## Stack

- Python 3.11+, `uv`
- `anthropic` / `openai` / `google-genai` (pluggable providers)
- `feedparser`, `pydantic`, `python-frontmatter`, `rich`

## Self-hosting (Docker + Coolify)

```bash
# runs daily at 06:00 UTC via supercronic
docker compose up -d
```

Set `ANTHROPIC_API_KEY` in environment or Coolify UI. Data persists in `cosmosphere_data` volume.

## Tuning taste

Edit `prompts/astro_taste_expert.md` or `prompts/astro_taste_amateur.md`. No code changes needed.

## State

- `data/seen.json` — processed arxiv IDs; delete to re-score everything
- `data/digests/` — daily digests
- `data/explanations/` — per-paper deep dives
- `data/posts/` — generated blog posts
- `data/weekly/` — weekly roundups

## Tests

```bash
uv run pytest
```

## Roadmap

- [x] arxiv astro-ph.HE ingestion
- [x] Multi-provider LLM scoring (Anthropic, OpenAI, Gemini, Claude Code)
- [x] Expert + amateur modes
- [x] `explain` — deep-dive single paper
- [x] `post` — blog post generator
- [x] `weekly` — weekly roundup
- [x] NASA APOD integration (`--apod`)
- [x] Desktop notifications (`--notify`)
- [x] Blog publish via git (`--publish`)
- [x] Docker + Coolify deploy
- [ ] NASA APOD LLM commentary
- [ ] JPL minor body alerts source
- [ ] RSS output for feed readers
- [ ] n8n workflow wrapper
