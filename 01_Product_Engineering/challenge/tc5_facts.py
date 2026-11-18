"""Score the TC5 several-lookups answer: six facts, right or wrong, no model.

The request asks, for three hires, which role to use and whether the standard gives a
company mailbox. The expected values come from the synthetic standard the corpus is built
from (standard_v0_1.md):

- role: the row of STD-role-list the hire's title maps to;
- mailbox: the standard has no mailbox column and never mentions one, so the right answer
  for every hire is that the standard does not say. A yes is wrong, and so is a flat no.

A fact is right only if the answer states the correct value for the correct hire. Naming
the value in order to reject it ("do not use Front Desk Associate") is wrong.

This is a text check with fixed patterns, not a judge. It can misread an unusual phrasing,
so the saved answers should be read by hand as well.

    python tc5_facts.py ../../use_case/evals/tc5_measure_graded_*.jsonl           # re-score saved rows
    python tc5_facts.py --write ../../use_case/evals/tc5_measure_graded_*.jsonl   # and save the scores
"""

import json
import re
import sys

UNSTATED = "not stated"

# anchor: how an answer refers to the hire. role: the standard role to use.
HIRES = {
    "hospitality": {"anchor": r"hospitality\s+associate|front\s+desk\s+associate",
                    "role": "Front Desk Associate", "mailbox": UNSTATED},
    "lifeguard": {"anchor": r"lifeguard", "role": "Lifeguard", "mailbox": UNSTATED},
    "trainer": {"anchor": r"personal\s+trainer", "role": "Personal Trainer", "mailbox": UNSTATED},
}

# The role name as a value. For the trainer the level is not part of the role, so
# "Personal Trainer Level 2" and "Level 2 Personal Trainer" are the title, not the role.
ROLE_VALUE = {
    "hospitality": r"front\s+desk\s+associate",
    "lifeguard": r"lifeguard",
    "trainer": r"(?<!level\s\d\s)(?<!l\d\s)personal\s+trainer(?!s?\W{0,3}(?:level|lvl|l)\W?\d)",
}
# For these two the title and the role share a name, so a bare mention is not an answer:
# the name has to follow a cue, or appear twice in one statement (label, then value).
NEEDS_CUE = {"lifeguard", "trainer"}
ROLE_CUE = r"(?:\brole\b|\buse[sd]?\b|\busing\b|→|->|=>|\bmaps?\s+to\b|\bmapped\s+to\b|\bassign\w*|:)[^.\n]{0,40}$"
SAME_AS_TITLE = (r"already\s+a\s+standard\s+role|is\s+a\s+standard\s+role|exact\s+match|direct\s+match|as[- ]is\b|"
                 r"same\s+(?:name|role|title)|unchanged|maps?\s+directly|matches\s+the\s+standard")
# A rejection is a negation right before the name, with only words like "use" or "the" between:
# "do not use X", "not X", "rather than X". "I can't give the Lifeguard answer" is not one.
REJECT_BEFORE = (r"(?:\bnot\b|n't\b|\bnever\b|\brather\s+than\b|\binstead\s+of\b|\bavoid\b|\bno\s+longer\b)"
                 r"(?:\s+(?:to|use|using|used|assign|assigning|map|pick|choose|select|be|as|a|an|the|role|called))*"
                 r"\W{0,3}$")
REJECT_AFTER = r"^\W{0,3}(?:is|are|would\s+be|should|must)\s*(?:not\b|n't\b|wrong\b|incorrect\b)"

MAILBOX = r"mailbox|mail\s+account|e-?mail\s+account|inbox"
GLOBAL = (r"all\s+(?:three|3)|any\s+of|none\s+of|each\s+(?:of|one|hire|role)|these\s+(?:roles|hires|three|titles)|"
          r"the\s+three|every(?:one)?\b|\bcolumn\b|any\s+role|all\s+roles|at\s+all\b|anywhere|nowhere|mailboxes")
SAYS_NOTHING = (
    r"(?:does\s*n[o']t|do\s*n[o']t|did\s*n[o']t|never|\bno\b|without)\s+(?:\w+\s+){0,3}?"
    r"(?:say|specif|mention|address|cover|state|includ|defin|list|contain|indicat|record|document|speak|refer)|"
    r"\bnot\s+(?:\w+\s+){0,2}?(?:stated|specified|covered|addressed|mentioned|defined|listed|documented|recorded|"
    r"in\s+the\s+standard|part\s+of\s+the\s+standard|something\s+the\s+standard)|"
    r"\bsilent\b|\bno\s+(?:information|mention|column|rule|guidance|entry|data|field|reference|basis|evidence)|"
    r"nothing\s+(?:about|on|regarding)|can(?:no|')t\s+(?:confirm|determine|say|tell|answer)|unable\s+to|"
    r"\bunknown\b|\bunclear\b|\bn/a\b|outside\s+(?:the\s+)?(?:standard|scope)|not\s+enough|no\s+way\s+to|"
    r"\bonly\s+(?:covers?|says?|lists?|records?|addresses)|\bcovers?\s+only|rule\s+(?:one|it|that|this)\s+out|"
    r"either\s+way|(?:n't|\bnot|\bnor)\s+(?:\w+\s+)?withhold")
# A yes or a no has to be about getting a mailbox: a label ("Company mailbox: yes") or a verb of
# giving next to the word. "That field is not a mailbox entitlement" is neither.
LABEL = r"^\W*(?:[\w ?'/-]{0,40}:)?\W*"
LEADING_YES = LABEL + r"(?:yes\b|✅)"
LEADING_NO = LABEL + r"(?:no\b|❌|✗)"
GIVE = r"(?:gets?|receiv\w*|given|gives?|provid\w*|includ\w*|has|have|comes?\s+with|entitled\s+to|eligible\s+for)"
MAILBOX_NOUN = r"(?:mailbox|mail\s+account|e-?mail\s+account|inbox)"
NOT_GIVEN = (r"(?:\bnot\b|n't\b|\bno\b|\bnever\b|\bwithout\b|\bneither\b|\bnor\b)\s+(?:\w+\s+){0,3}?" + GIVE +
             r"\s+(?:\w+\s+){0,4}?" + MAILBOX_NOUN + r"|\b" + GIVE + r"\s+no\s+(?:\w+\s+){0,2}?" + MAILBOX_NOUN +
             r"|\bno\s+(?:company\s+|corporate\s+|work\s+)?" + MAILBOX_NOUN + r"\s+(?:is|are)\s+(?:given|provided|issued)")
IS_GIVEN = r"\b" + GIVE + r"\s+(?:\w+\s+){0,4}?" + MAILBOX_NOUN


def _expand_tables(text: str) -> str:
    """Turn each markdown table row into 'Header: cell' lines, so a cell keeps its column's meaning."""
    out, header = [], None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if header is None:
                header = cells
            elif not all(re.fullmatch(r":?-+:?", cell or "-") for cell in cells):
                out.append(" ; ".join(f"{head}: {cell}" for head, cell in zip(header, cells)))
        else:
            header = None
            out.append(line)
    return "\n".join(out)


def _statements(answer: str) -> list[tuple[str, set[str]]]:
    """Split into statements and say which hires each one is about.

    A statement that names a hire is about that hire. One that names nobody is about all three
    if it speaks generally ("any of these roles", "no column"), else about the hire of the
    statement before it, as a bullet under a heading is.
    """
    text = _expand_tables(answer.replace("’", "'").replace("**", "").replace("`", ""))
    out, current = [], set(HIRES)
    for piece in re.split(r"\n+|(?<=[.!?])\s+|\s;\s|;\s", text):
        statement = piece.strip().lower()
        if not statement:
            continue
        named = {key for key, hire in HIRES.items() if re.search(hire["anchor"], statement)}
        if named:
            current = named
            about = named
        elif re.search(GLOBAL, statement):
            about = set(HIRES)
        else:
            about = current
        out.append((statement, about))
    return out


def _role_found(key: str, statements) -> str | None:
    """'stated', 'rejected' or None for the expected role, in the statements about this hire."""
    stated = rejected = False
    for statement, about in statements:
        if key not in about:
            continue
        matches = list(re.finditer(ROLE_VALUE[key], statement))
        if key == "lifeguard" and re.search(SAME_AS_TITLE, statement) and matches:
            stated = True
        for match in matches:
            before, after = statement[:match.start()], statement[match.end():]
            if re.search(REJECT_BEFORE, before) or re.search(REJECT_AFTER, after):
                rejected = True
            elif key not in NEEDS_CUE or re.search(ROLE_CUE, before) or (
                    len(list(re.finditer(HIRES[key]["anchor"], statement))) > 1 and match is matches[-1]):
                stated = True
    return "rejected" if rejected else "stated" if stated else None


def _mailbox_value(statement: str) -> str | None:
    if not re.search(MAILBOX, statement) or statement.endswith("?"):
        return None
    if re.search(LEADING_YES, statement):
        return "yes"
    if re.search(SAYS_NOTHING, statement):
        return UNSTATED
    if re.search(LEADING_NO, statement) or re.search(NOT_GIVEN, statement):
        return "no"
    if re.search(IS_GIVEN, statement):
        return "yes"
    return None


def _mailbox_found(key: str, statements) -> str | None:
    values = {value for statement, about in statements if key in about
              for value in [_mailbox_value(statement)] if value}
    return "mixed" if len(values) > 1 else next(iter(values), None)


def score_several_lookups(answer: str) -> dict:
    """Right or wrong for each of the six facts, the count out of 6, and what the scorer read."""
    statements = _statements(answer or "")
    facts, found = {}, {}
    for key, hire in HIRES.items():
        found[f"{key}_role"] = _role_found(key, statements)
        found[f"{key}_mailbox"] = _mailbox_found(key, statements)
        facts[f"{key}_role"] = found[f"{key}_role"] == "stated"
        facts[f"{key}_mailbox"] = found[f"{key}_mailbox"] == hire["mailbox"]
    return {"facts": facts, "facts_right": sum(facts.values()), "found": found}


def main(args: list[str]) -> None:
    """Re-score saved several-lookups rows from their stored answer text. No model is called.

    With --write, the facts fields in each file are replaced by this scorer's reading of the
    saved answer. Nothing else in a row changes."""
    write = "--write" in args
    for path in (arg for arg in args if arg != "--write"):
        rows = [json.loads(line) for line in open(path)]
        for row in rows:
            if row.get("request") == "several lookups" and "answer" in row:
                score = score_several_lookups(row["answer"])
                row.update(facts=score["facts"], facts_right=score["facts_right"], facts_found=score["found"])
                wrong = [name for name, right in score["facts"].items() if not right]
                print(f"{path.rsplit('/', 1)[-1]}\t{row['way']}\t{score['facts_right']}/6\twrong: {wrong or 'none'}")
        if write:
            with open(path, "w") as handle:
                handle.writelines(json.dumps(row) + "\n" for row in rows)


if __name__ == "__main__":
    main(sys.argv[1:])
