"""Entry point: `python -m cosmosphere <cmd>` or `cosmosphere <cmd>`."""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

from dotenv import load_dotenv
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from .analyze import AnalyzeError, score_papers
from .apod import ApodError, fetch_apod, render_apod_markdown
from .explain import ExplainError, explain_paper
from .fetch import FetchError, fetch_papers
from .generate import write_digest
from .notify import maybe_notify
from .post import PostError, generate_post
from .providers import AVAILABLE_PROVIDERS
from .publish import PublishError, publish_to_blog
from .state import load_seen, save_seen
from .weekly import WeeklyError, generate_weekly

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
SEEN_PATH = DATA_DIR / "seen.json"
DIGEST_DIR = DATA_DIR / "digests"

DEFAULT_THRESHOLD = 7

console = Console()


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )


def _resolve_lang(lang: str | None) -> str:
    return lang or "en"


# ---------- run ----------

def cmd_run(args) -> int:
    load_dotenv(ROOT / ".env")
    lang = _resolve_lang(args.lang)
    threshold = args.threshold

    seen = load_seen(SEEN_PATH)
    console.print(f"[dim]Loaded {len(seen)} previously-seen IDs[/dim]")

    apod_block: str | None = None
    if args.apod:
        try:
            apod = fetch_apod()
            if apod:
                apod_block = render_apod_markdown(apod)
                console.print(f"[dim]APOD: {apod['title']}[/dim]")
        except ApodError as e:
            console.print(f"[yellow]APOD fetch failed (non-fatal):[/yellow] {e}")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        t = progress.add_task("Fetching arxiv astro-ph.HE RSS...", total=None)
        try:
            papers = fetch_papers(seen)
        except FetchError as e:
            console.print(f"[red]Fetch failed:[/red] {e}")
            return 2
        progress.update(t, description=f"Fetched {len(papers)} new papers")

        if not papers:
            console.print("[yellow]No new papers today.[/yellow]")
            if apod_block:
                out_path = write_digest([], DIGEST_DIR, apod_block=apod_block)
                console.print(f"[green]APOD-only digest at {out_path}[/green]")
            return 0

        progress.add_task(
            f"Scoring {len(papers)} papers via {args.provider} [{args.mode}/{lang}]...",
            total=None,
        )
        try:
            scored = score_papers(
                papers, provider=args.provider, mode=args.mode, lang=lang
            )
        except AnalyzeError as e:
            console.print(f"[red]Scoring failed:[/red] {e}")
            return 3

    kept = [p for p in scored if p.relevance_score >= threshold]
    out_path = write_digest(
        kept,
        DIGEST_DIR,
        apod_block=apod_block,
        extra_meta={"mode": args.mode, "lang": lang, "threshold": threshold},
    )

    seen.update(p.arxiv_id for p in papers)
    save_seen(SEEN_PATH, seen)

    if args.notify:
        sent = maybe_notify(scored)
        if sent:
            console.print(f"[dim]Sent {sent} notification(s)[/dim]")

    if args.publish:
        try:
            dest = publish_to_blog(
                out_path,
                subdir="digest",
                commit_msg=f"digest: {date.today().isoformat()}",
            )
            console.print(f"[green]Published to {dest}[/green]")
        except PublishError as e:
            console.print(f"[red]Publish failed:[/red] {e}")
            return 4

    console.print(
        Panel.fit(
            f"[bold green]Digest written[/bold green]\n"
            f"  Path:      {out_path}\n"
            f"  Provider:  {args.provider} [{args.mode}/{lang}]\n"
            f"  Fetched:   {len(papers)}\n"
            f"  Scored:    {len(scored)}\n"
            f"  Kept >={threshold}: {len(kept)}\n"
            f"  APOD:      {'yes' if apod_block else 'no'}\n"
            f"  Seen DB:   {len(seen)} total IDs",
            title="cosmosphere",
            border_style="cyan",
        )
    )
    return 0


# ---------- explain ----------

def cmd_explain(args) -> int:
    load_dotenv(ROOT / ".env")
    lang = _resolve_lang(args.lang)
    try:
        out_path, text = explain_paper(
            args.arxiv_id,
            provider=args.provider,
            mode=args.mode,
            lang=lang,
        )
    except ExplainError as e:
        console.print(f"[red]Explain failed:[/red] {e}")
        return 2

    console.print(text)
    console.print(
        Panel.fit(f"Saved to {out_path}", title="cosmosphere explain", border_style="cyan")
    )
    return 0


# ---------- post ----------

def cmd_post(args) -> int:
    load_dotenv(ROOT / ".env")
    lang = _resolve_lang(args.lang)
    target = date.fromisoformat(args.date) if args.date else date.today()
    try:
        out_path = generate_post(
            target_date=target,
            provider=args.provider,
            mode=args.mode,
            lang=lang,
            publish=args.publish,
        )
    except PostError as e:
        console.print(f"[red]Post failed:[/red] {e}")
        return 2

    console.print(
        Panel.fit(
            f"Post written to {out_path}" + ("\nPublished to blog." if args.publish else ""),
            title="cosmosphere post",
            border_style="cyan",
        )
    )
    return 0


# ---------- weekly ----------

def cmd_weekly(args) -> int:
    load_dotenv(ROOT / ".env")
    lang = _resolve_lang(args.lang)
    try:
        out_path = generate_weekly(
            provider=args.provider,
            mode=args.mode,
            lang=lang,
            publish=args.publish,
        )
    except WeeklyError as e:
        console.print(f"[red]Weekly failed:[/red] {e}")
        return 2

    console.print(
        Panel.fit(
            f"Weekly written to {out_path}" + ("\nPublished." if args.publish else ""),
            title="cosmosphere weekly",
            border_style="cyan",
        )
    )
    return 0


# ---------- parser ----------

def _add_common(p: argparse.ArgumentParser) -> None:
    p.add_argument("-v", "--verbose", action="store_true")
    p.add_argument("--provider", choices=AVAILABLE_PROVIDERS, default="anthropic")
    p.add_argument("--mode", choices=["expert", "amateur"], default="expert")
    p.add_argument(
        "--lang",
        choices=["pl", "en"],
        default=None,
        help="Output language (default: en)",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="cosmosphere", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    # run
    p_run = sub.add_parser("run", help="Fetch, score, write today's digest")
    _add_common(p_run)
    p_run.add_argument(
        "--threshold", type=int, default=DEFAULT_THRESHOLD,
        help=f"Minimum score to include (default: {DEFAULT_THRESHOLD})",
    )
    p_run.add_argument("--notify", action="store_true",
                       help="Send notify-send for papers scoring >=9")
    p_run.add_argument("--apod", action="store_true",
                       help="Prepend NASA Astronomy Picture of the Day to digest")
    p_run.add_argument("--publish", action="store_true",
                       help="Copy digest to Quartz blog repo and git push")

    # explain
    p_ex = sub.add_parser("explain", help="Deep-dive a single paper by arxiv id")
    _add_common(p_ex)
    p_ex.add_argument("arxiv_id", help="arxiv id like 2504.12345")

    # post
    p_post = sub.add_parser("post", help="Generate a ~500-word blog post from a digest")
    _add_common(p_post)
    p_post.add_argument("--date", help="YYYY-MM-DD (default: today)")
    p_post.add_argument("--publish", action="store_true")

    # weekly
    p_wk = sub.add_parser("weekly", help="Weekly roundup from last 7 days of digests")
    _add_common(p_wk)
    p_wk.add_argument("--publish", action="store_true")

    args = parser.parse_args(argv)
    _setup_logging(getattr(args, "verbose", False))

    dispatch = {
        "run": cmd_run,
        "explain": cmd_explain,
        "post": cmd_post,
        "weekly": cmd_weekly,
    }
    fn = dispatch.get(args.cmd)
    if fn is None:
        parser.error(f"Unknown command: {args.cmd}")
        return 1
    return fn(args)


if __name__ == "__main__":
    sys.exit(main())
