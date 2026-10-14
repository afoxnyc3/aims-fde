"""Render golden.jsonl as a printable page for a stakeholder review.

Each golden becomes one page: the ticket as an associate would read it in JSM,
then the proposed outcome in plain words. The `why` field is hidden by default
so the reviewer judges the output without being told the intended answer.

    python3 use_case/evals/render_goldens.py              # writes goldens_review.html
    python3 use_case/evals/render_goldens.py --show-why   # includes the rationale

Open the HTML in a browser and print it, or share the screen.
"""

import argparse
import json
import re
from html import escape
from pathlib import Path

HERE = Path(__file__).parent

STATUS_LABELS = {
    "recommended": "Recommended access",
    "needs_information": "Needs more information",
    "human_review": "Needs human review",
    "ignored": "Ignored (no action, no comment)",
    "failed": "Failed",
}
REVIEW_LABELS = {
    "ambiguous_identity": "unclear who the new hire is",
    "ambiguous_mapping": "unclear which standard role applies",
    "exception": "request goes beyond the standard",
}


def ticket_sections(text: str) -> list[tuple[str, str]]:
    """Split ticket_text on its [title] / [description] / [field: X] labels."""
    parts = re.split(r"^\[([^\]]+)\]\s*$", text, flags=re.MULTILINE)
    sections = [("", parts[0].strip())] if parts[0].strip() else []
    for label, body in zip(parts[1::2], parts[2::2]):
        label = label.removeprefix("field: ").strip().capitalize()
        sections.append((label, body.strip().replace("\\[", "[").replace("\\]", "]")))
    return sections


def render_ticket(request: dict) -> str:
    rows = []
    for label, body in ticket_sections(request["ticket_text"]):
        if label == "Description":
            lines = [line for line in body.splitlines() if line.strip()]
            body_html = "<br>".join(escape(line) for line in lines)
        else:
            body_html = escape(body) or "<em>(blank)</em>"
        rows.append(f"<tr><th>{escape(label)}</th><td>{body_html}</td></tr>")
    html = f"<table class='ticket'>{''.join(rows)}</table>"

    comments = request.get("comments", [])
    if comments:
        items = []
        for c in comments:
            who = {"agent": "Automated workflow", "human": "Person"}.get(c["author_type"], "Unknown author")
            items.append(
                f"<li><span class='meta'>{escape(who)} ({escape(c.get('author_id') or 'no ID')}) · "
                f"{escape(c['created_at'])}</span><br>{escape(c['text'])}</li>"
            )
        html += f"<h4>Comments</h4><ol class='comments'>{''.join(items)}</ol>"
    else:
        html += "<p class='meta'>No comments.</p>"
    return html


def render_access(rec: dict, heading: str) -> str:
    def scoped(item: dict, key: str) -> str:
        scope = item.get("scope")
        where = f" at {scope['name']}" if scope else " (system-wide)"
        return escape(item[key]["name"] + where)

    rows = [
        ("Person", rec["person_name"]),
        ("Job title", rec["job_title"]),
        ("Start date", rec["start_date"]),
        ("Login email", rec["login_email"]),
        ("Venues", ", ".join(v["name"] for v in rec["venues"])),
        ("Standard version", rec["standard_version"]),
    ]
    html = f"<h4>{escape(heading)}</h4><table class='access'>"
    html += "".join(f"<tr><th>{escape(k)}</th><td>{escape(str(v))}</td></tr>" for k, v in rows)
    roles = "<br>".join(scoped(a, "role") for a in rec["assignments"])
    html += f"<tr><th>Roles</th><td>{roles}</td></tr>"
    if rec.get("staff_groups"):
        groups = "<br>".join(scoped(g, "staff_group") for g in rec["staff_groups"])
        html += f"<tr><th>Staff groups</th><td>{groups}</td></tr>"
    html += "</table>"
    steps = "".join(f"<li>{escape(s)}</li>" for s in rec["proposed_changes"])
    return html + f"<h4>Steps for the associate</h4><ol>{steps}</ol>"


def render_outcome(response: dict) -> str:
    status = response["status"]
    label = STATUS_LABELS.get(status, status)
    if response.get("review_reason"):
        label += f": {REVIEW_LABELS.get(response['review_reason'], response['review_reason'])}"
    html = f"<p class='status status-{escape(status)}'>{escape(label)}</p>"
    html += f"<p><strong>Reason:</strong> {escape(response['rationale'])}</p>"

    if response.get("missing_fields"):
        missing = ", ".join(f.replace("_", " ") for f in response["missing_fields"])
        html += f"<p><strong>Missing:</strong> {escape(missing)}</p>"
    if response.get("answer"):
        html += render_access(response["answer"], "Proposed access")
    if response.get("standard_proposal"):
        html += render_access(response["standard_proposal"], "Standard baseline (not approved for the exception)")
    if response.get("exception_difference"):
        diffs = "".join(f"<li>{escape(d)}</li>" for d in response["exception_difference"])
        owner = response.get("approval_owner_role") or "Unknown"
        html += f"<h4>Outside the standard</h4><ul>{diffs}</ul><p><strong>Who approves:</strong> {escape(owner)}</p>"
    if response.get("caveats"):
        cav = "".join(f"<li>{escape(c)}</li>" for c in response["caveats"])
        html += f"<h4>Caveats</h4><ul>{cav}</ul>"

    comment = response.get("jira_comment")
    html += (
        f"<h4>Comment that would be posted on the ticket</h4><blockquote>{escape(comment)}</blockquote>"
        if comment else "<p class='meta'>No comment would be posted on the ticket.</p>"
    )
    return html


def render_page(goldens: list[dict], show_why: bool) -> str:
    pages = []
    for number, golden in enumerate(goldens, 1):
        ref = golden["input"]["ticket_ref"]
        why = f"<h3>Why this is the intended answer</h3><p>{escape(golden['why'])}</p>" if show_why else ""
        pages.append(
            f"<section><h2>Example {number} · {escape(ref)}</h2>"
            f"<div class='cols'><div><h3>The ticket</h3>{render_ticket(golden['input'])}</div>"
            f"<div><h3>What the tool proposes</h3>{render_outcome(golden['output'])}</div></div>"
            f"{why}<div class='ask'>Would you accept this as written? &nbsp; Yes / No / Partly"
            f"<br>If not, what would you change?<div class='lines'></div></div></section>"
        )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Golden examples review</title>
<style>
  body {{ font: 14px/1.45 system-ui, sans-serif; color: #1d2a33; margin: 24px; }}
  section {{ page-break-after: always; margin-bottom: 48px; }}
  h2 {{ border-bottom: 2px solid #2c5f63; padding-bottom: 4px; }}
  h3 {{ margin: 0 0 8px; color: #2c5f63; }} h4 {{ margin: 14px 0 6px; }}
  .cols {{ display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; vertical-align: top; padding: 4px 8px; border-bottom: 1px solid #e3e8ea; }}
  th {{ width: 32%; color: #51636d; font-weight: 600; }}
  .meta {{ color: #51636d; font-size: 12px; }}
  .comments li {{ margin-bottom: 8px; }}
  .status {{ display: inline-block; padding: 4px 10px; border-radius: 4px; font-weight: 600; background: #e3e8ea; }}
  .status-recommended {{ background: #dcefe3; }} .status-needs_information {{ background: #fdf0d5; }}
  .status-human_review {{ background: #fde2d5; }} .status-failed {{ background: #f6d5d5; }}
  blockquote {{ margin: 0; padding: 8px 12px; background: #f4f6f7; border-left: 3px solid #2c5f63; }}
  .ask {{ margin-top: 20px; padding: 12px; border: 1px dashed #51636d; }}
  .lines {{ height: 72px; }}
  @media print {{ body {{ margin: 0; }} .cols {{ gap: 16px; }} }}
</style></head><body>{"".join(pages)}</body></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--input", type=Path, default=HERE / "golden.jsonl")
    parser.add_argument("--output", type=Path, default=HERE / "goldens_review.html")
    parser.add_argument("--show-why", action="store_true", help="include each golden's why field")
    args = parser.parse_args()

    goldens = [json.loads(line) for line in args.input.read_text(encoding="utf-8").splitlines() if line.strip()]
    args.output.write_text(render_page(goldens, args.show_why), encoding="utf-8")
    print(f"Wrote {len(goldens)} examples to {args.output}")


if __name__ == "__main__":
    main()
