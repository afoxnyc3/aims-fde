"""The retrieval corpus: synthetic tickets and the draft standard as named pages.

One page per verified TC2 ticket, plus one page per section of the draft
standard. Every page has a stable name, headings, and a line in an index page,
which is what direct corpus interaction (list / grep / read) needs. The same
pages are the chunks for BM25 and dense search: one record is one unit, the
boundary the data already gives.

The data file is gitignored and never copied into the image. It is read from
CORPUS_PATH, mounted at runtime.
"""

import hashlib
import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).parent
DEFAULT_CORPUS_PATH = HERE.parent.parent / "use_case" / "data" / "synthetic_v1.jsonl"
STANDARD_PATH = HERE / "standard_v0_1.md"


@dataclass(frozen=True)
class Page:
    """One retrievable record. `name` is the id every answer cites."""

    name: str
    title: str
    text: str


class CorpusMissing(Exception):
    """The data file is not where CORPUS_PATH points, so nothing can be retrieved."""


def ticket_page_name(row_id: str) -> str:
    # Hashed rather than row_id itself: row_id spells out the generation axes
    # ("outside_standard|returning_or_moving|..."), so grep would find the label
    # instead of the evidence. The hash is stable for as long as row_id is.
    return "SYN-" + hashlib.sha1(row_id.encode()).hexdigest()[:6]


def _outcome_lines(row: dict) -> list[str]:
    # The routed outcome is in the corpus on purpose: "how did we handle a
    # ticket like this?" is a precedent question associates ask, and a closed
    # JSM ticket carries its resolution. These are draft-rule labels, not
    # ratified decisions, and the heading says so.
    lines = [f"Status: {row['expected_status']}"]
    if row.get("expected_reason"):
        lines.append(f"Reason: {row['expected_reason']}")
    if row.get("expected_caveat"):
        lines.append(f"Caveat: {row['expected_caveat']}")
    proposal = row.get("expected_proposal")
    if proposal:
        login = "yes" if proposal.get("login_required") else "no"
        lines.append(
            f"Proposed: {proposal.get('standard_role')} at {proposal.get('club')}; "
            f"staff login {login}; member record yes"
        )
        if proposal.get("extra_requests"):
            lines.append("Requested beyond the standard: " + "; ".join(proposal["extra_requests"]))
    return lines


def render_ticket(row: dict) -> Page:
    """Turn one generated ticket into a page with fixed headings."""
    ticket = row["ticket"]
    name = ticket_page_name(row["row_id"])
    fields = {**ticket.get("fields", {}), **ticket.get("form", {})}
    field_lines = [f"- {key}: {value}" for key, value in fields.items() if value not in ("", None)]
    comment_lines = [
        f"- {comment.get('timestamp', '')} ({comment.get('author_role', 'unknown')}): {comment.get('body', '')}"
        for comment in ticket.get("comments", [])
    ]
    sections = [
        f"# {name}: {ticket['summary']}",
        f"## Summary\nRequest type: {ticket.get('request_type', '')}\n"
        f"Created: {ticket.get('created', '')}\n{ticket['summary']}",
        "## Form fields\n" + ("\n".join(field_lines) or "(none filled)"),
        "## Notes\n" + (ticket.get("notes") or "(none)"),
        "## Comments\n" + ("\n".join(comment_lines) or "(none)"),
        "## Outcome (draft rule)\n" + "\n".join(_outcome_lines(row)),
    ]
    return Page(name=name, title=ticket["summary"], text="\n\n".join(sections))


def load_standard_pages(path: Path = STANDARD_PATH) -> list[Page]:
    """Split the standard file into pages at each `## STD-...` heading."""
    pages = []
    for block in re.split(r"^## ", path.read_text(encoding="utf-8"), flags=re.MULTILINE)[1:]:
        heading, _, body = block.partition("\n")
        name, _, title = heading.partition(" ")
        pages.append(Page(name=name, title=title.strip(), text=f"# {name}: {title.strip()}\n{body.strip()}"))
    return pages


def load_ticket_pages(path: Path) -> list[Page]:
    """Verified rows only: the file also keeps the one refused row, unlabelled."""
    if not path.exists():
        raise CorpusMissing(f"corpus file not found: {path} (set CORPUS_PATH)")
    pages = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                if row.get("verified"):
                    pages.append(render_ticket(row))
    return pages


def build_index(pages: list[Page]) -> str:
    """The index page: one line per page, the entry point for `list_pages`."""
    lines = ["# Index", "", "Standard pages (draft v0.1) and synthetic onboarding tickets.", ""]
    lines += [f"- {page.name}: {page.title}" for page in pages]
    return "\n".join(lines)


def load_corpus(path: Path | None = None) -> list[Page]:
    """Standard pages first, then tickets. Names are unique or this raises."""
    path = Path(path or os.getenv("CORPUS_PATH") or DEFAULT_CORPUS_PATH)
    pages = load_standard_pages() + load_ticket_pages(path)
    names = [page.name for page in pages]
    if len(names) != len(set(names)):
        raise ValueError("page names collide; widen the hash in ticket_page_name")
    return pages
