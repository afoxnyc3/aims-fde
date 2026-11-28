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

# title: how an answer names the hire. role: the standard role to use.
HIRES = {
    "hospitality": {"title": r"hospitality\s+associate", "role": "Front Desk Associate", "mailbox": UNSTATED},
    "lifeguard": {"title": r"lifeguard", "role": "Lifeguard", "mailbox": UNSTATED},
    "trainer": {"title": r"personal\s+trainer", "role": "Personal Trainer", "mailbox": UNSTATED},
}

# The role name as a value. For the trainer the level is not part of the role, so
# "Personal Trainer Level 2" and "Level 2 Personal Trainer" are the title, not the role.
# "Lifeguard Supervisor" or "Front Desk Associate Lead" is a different role name, not the role.
LONGER = r"(?!\s+(?:supervisor|lead|leader|manager|assistant|senior|junior|trainee|coordinator|captain|ii|iii|[1-9])\b)"
ROLE_VALUE = {
    "hospitality": r"front\s+desk\s+associate" + LONGER,
    "lifeguard": r"lifeguard" + LONGER,
    "trainer": r"(?<!level\s\d\s)(?<!l\d\s)personal\s+trainer(?!s?\W{0,3}(?:level|lvl|l)\W?\d)" + LONGER,
}
# A role counts as stated only right after a cue in the same clause ("use X", "Role: X", "maps to X").
# A bare mention does not count: two of the titles are also role names, and a role can be named for
# another purpose ("Front Desk Associate gets a login").
# The cue has to sit right before the name, with only small words between ("role to use: X").
# "the role for the Lifeguard" is not one. A colon or dash is a cue only after the hire's own
# title ("Lifeguard: Lifeguard"), so "Hire: Lifeguard" does not state the role.
ROLE_CUE = (r"(?:\brole\b|\buses?\b|\busing\b|→|->|=>|\bmaps?\s+to\b|\bmapped\s+to\b|\bassign\w*|"
            r"\bset\s+up\s+as\b)(?:\s*[:=]|\s+(?:to|use|is|be|the|a|an|as|would|should|will|standard|role)\b|"
            r"[\s\"'(\[]){0,8}$")
AFTER_TITLE = r"[^.,;:|\n]{0,25}(?::|\s[—–-]\s)[\s\"'(\[]{0,3}$"
# A rejection is a negation right before the name, with only words like "use" or "the" between
# ("do not use X", "not X", "rather than X"), or a verdict right after it ("X is not the role",
# "X would be the wrong choice", "X does not apply"). "I can't give the Lifeguard answer" is neither.
# A prohibition is a rejection too ("it is forbidden to use X", "you are not allowed to use X",
# "under no circumstances use X", "stop using X", "X is prohibited", "X must be avoided").
PROHIBIT = (r"forbid\w*|forbade|prohibit\w*|disallow\w*|bann?ed|bans?|barr?ed|bars?|impermissible|unacceptable|"
            r"incorrect|invalid|improper|inappropriate|mistake|error|off[\s-]limits|ruled\s+out|not\s+allowed|"
            r"not\s+permitted|avoided|illegal|unlawful|violat\w+|unwise|ill-?advised|discourag\w+")
REJECT_BEFORE = (r"(?:\bnot\b|n't\b|\bcannot\b|\bnever\b|\brather\s+than\b|\binstead\s+of\b|\bavoid\w*|"
                 r"\bno\s+longer\b|\bwrong\b|\bother\s+than\b|\bno\s+role\b|\b(?:" + PROHIBIT + r")\b|"
                 r"\bno\s+circumstances?\b|\bno\s+means\b|\bno\s+case\b|\bnobody\b|\bno\s+one\b|\bnone\b|"
                 r"\brefrain\w*|\bstop\w*|\bagainst\b|\bsteer\s+clear\b|\bprevent\w*)"
                 r"(?:\s+(?:to|use|using|used|assign|assigning|assigned|map|mapped|mapping|pick|picking|choose|"
                 r"choosing|select|selecting|be|as|a|an|the|role|called|allowed|permitted|supposed|meant|able|ok|okay|"
                 r"acceptable|correct|right|valid|appropriate|possible|advisable|recommended|you|we|i|anyone|should|"
                 r"must|may|can|ever|from|of|for))*"
                 r"\W{0,3}$")
# "A Lifeguard does not get a mailbox" is about the mailbox, so the verdict has to be about the role.
REJECT_AFTER = (r"^\W{0,3}(?:(?:is|are|was|would\s+be)\s*(?:not|n't)\s+(?:the|a|an|correct|right|valid|appropriate|"
                r"used|to\s+be\s+used|what)\b|(?:is|are|was|would\s+be)\s+(?:the\s+|a\s+|an\s+)?(?:wrong|incorrect)\b|"
                r"(?:should|must|can|ca|may|could|shall|might|will|wo|would)\s*(?:not|n't|\s+never)\s+be\s+(?:used|assigned|chosen|picked|selected)|no\s+longer\s+exists?|"
                r"[^.;]{0,40}\b(?:is|was|would\s+be)\s+(?:a\s+mistake|wrong|incorrect)\b|"
                r"(?:does|do|would)\s*(?:not|n't)\s+(?:apply|fit|match|exist))")

# The two rules above need the negation right next to the name. These two do not.
# Before the name: a negation or prohibition anywhere earlier in the same stretch of the sentence, when
# the name follows a role cue ("I would not recommend that you use X", "do not, under any circumstances,
# use X"). The stretch starts again at a comma, a colon or a word like "so", so "the old title is not
# allowed, so use X" still states X. A comma right after the negation does not end it ("never, ever").
NEGATION = (r"(?:\bnot\b|n't\b|\bcannot\b|\bnever\b|\bno\s+(?:circumstances?|means|case|one|longer|way)\b|\bnobody\b|"
            r"\bnone\b|\bforbid\w*|\bforbade\b|\bprohibit\w*|\bdisallow\w*|\bbann?ed\b|\bbarr?ed\b|\billegal\b|"
            r"\bunlawful\b|\bviolat\w+|\bunwise\b|\bill-?advised\b|\bdiscourag\w+|\bagainst\b)")
# A negation about the title, the level or the role list is not about the role that follows:
# "legacy title, not in the role list → X", "the level is not part of the role → X".
ABOUT_THE_TITLE = (r"\btitles?\b|\blegacy\b|\bnames?\b|\blevels?\b|role\s+list|\b(?:a|as\s+a)\s+role\b|\blisted\b|"
                   r"hospitality\s+associate")
DANGLING = r"(?:\bnot\b|n't\b|\bcannot\b|\bnever\b)"
STARTS_AGAIN = r"[,:]|\s[—–-]\s|→|->|=>|\b(?:so|but|instead|therefore|hence|thus|then|and)\b"
# After the name, in the rest of its clause: a prohibition in any form ("X (prohibited)", "X, which the
# standard prohibits", "X here violates the standard"), unless the words between are about something
# else ("X, because the old title is prohibited") or negate it ("X, never prohibited").
PROHIBIT_AFTER = r"\b(?:" + PROHIBIT + r"|prohibits?|forbids?|retired|deprecated|discontinued)\b"
# The sentence right after the one that states the role, on the same line, can take it back:
# "Use X. This role is prohibited." "Use X. That is not allowed." "Use X. Actually, don't."
TAKEN_BACK = (r"^\W*(?:(?:actually|no)\W+)?(?:(?:this|that|it)(?:\s+role)?(?:"
              r"(?:\s+(?:is|was|would\s+be)|'s)\s+(?:strictly\s+)?(?:a\s+)?(?:" + PROHIBIT + r"|wrong)\b|"
              r"(?:\s+(?:is|was|can|should|must|will)\s*(?:not|n't)|\s+(?:ca|wo)n't|'s\s+not|\s+cannot)\s+(?:be\s+)?"
              r"(?:the\s+)?(?:allowed|permitted|used|assigned|right|correct|valid)\b)|(?:don't|do\s+not)\W*$)")
# "It is incorrect to use the legacy title" is about the title, not the role just stated.
NOT_A_TAKE_BACK = r"\bto\s+\w+|\blevels?\b"
ABOUT_SOMETHING_ELSE = r"\btitles?\b|\blegacy\b|\bnames?\b|\bformer\b|hospitality\s+associate|\bticket\b"

# After the name, in the rest of the same clause: a verb with a negation ("is not in the standard",
# "has no entry", "was not found"), a bracket that opens with a doubt ("(not found ...", "(unconfirmed"),
# or an alternative or condition ("or Pool Attendant", "if it exists"). A clause about the login,
# mailbox, member record or club is left alone: "does not get a staff login" is not about the role.
DOUBT_AFTER = (r"\b(?:is|are|was|were|does|do|did|has|have|had|can|could|would|will)\s*(?:not\b|n't\b|no\b)|"
               r"\bcannot\b|\(\s*(?:not\b|no\b|un\w+|could\s*n|can\s*n)|^\W{0,3}(?:or|if)\b")
OTHER_TOPIC = r"mailbox|e-?mail|\blogin\b|member\s+record|\bclubs?\b"

MAILBOX_NOUN = r"(?:mailbox|mail\s+account|e-?mail\s+account|inbox)(?:e?s)?"
MAILBOX = r"mailbox|mail\s+account|e-?mail\s+account|inbox"
GLOBAL = (r"all\s+(?:three|3)|any\s+of|none\s+of|each\s+(?:of|one|hire|role)|these\s+(?:roles|hires|three|titles)|"
          r"the\s+three|every(?:one)?\b|\bcolumn\b|any\s+role|all\s+roles|at\s+all\b|anywhere|nowhere|mailboxes")
SAYS_NOTHING = (
    r"(?:does\s*n[o']t|do\s*n[o']t|did\s*n[o']t|never|\bno\b|without)\s+(?:\w+\s+){0,3}?"
    r"(?:say|specif|mention|address|cover|state|includ|defin|list|contain|indicat|record|document|speak|refer)|"
    r"\bnot\s+(?:\w+\s+){0,2}?(?:stated|specified|covered|addressed|mentioned|defined|listed|documented|recorded|"
    r"in\s+the\s+standard|part\s+of\s+the\s+standard|something\s+the\s+standard)|"
    r"\bsilent\b|\bno\s+(?:\w+\s+){0,2}?(?:information|mention|column|rule|guidance|entry|data|field|reference|basis|evidence)|"
    r"nothing\s+(?:about|on|regarding)|can(?:no|')t\s+(?:confirm|determine|say|tell|answer)|unable\s+to|"
    r"\bunknown\b|\bunclear\b|\bn/a\b|outside\s+(?:the\s+)?(?:standard|scope)|not\s+enough|no\s+way\s+to|"
    r"\bonly\s+(?:covers?|says?|lists?|records?|addresses)|\bcovers?\s+only|\bno\s+(?:\w+\s+){0,3}?entitlement")
# "It doesn't give a mailbox, and it doesn't rule one out" is the unstated answer, not a no.
NEITHER = (r"rule\s+(?:one|it|that|this)\s+out|either\s+way|(?:n't|\bnot|\bnor)\s+(?:\w+\s+)?withhold|"
           r"(?:n't|\bnot)\s+mean\b|(?:n't|\bnot)\s+(?:be\s+)?ruled\s+out")
# A yes or a no has to be about getting a mailbox: a label ("Company mailbox: yes") or a verb of
# giving next to the word. "That field is not a mailbox entitlement" is neither.
LABEL = r"^\W*(?:[\w ?'/-]{0,40}:)?\W*"
LEADING_YES = LABEL + r"(?:yes\b|✅)"
LEADING_NO = LABEL + r"(?:no\b(?!\s+(?:\w+\s+){0,3}?(?:information|mention|column|rule|guidance|entry|record))|❌|✗)"
GIVE = (r"(?:gets?|getting|receiv\w*|given|gives?|provid\w*|includ\w*|has|have|comes?\s+with|entitled\s+to|eligible\s+for|"
        r"issu\w+|assign\w*|grant\w*|allocat\w*|allot\w*|suppl\w+|offer\w*|provision\w*|award\w*|set\s+up\s+with|"
        r"ends?\s+up\s+with|qualif\w+\s+for|count\s+on)")
# "one" standing for the mailbox, only where the clause ends or goes on about when or how:
# "all three get one", "get one on their first day". Not "gets one member record" or "has one row".
ONE = (r"(?<!each\s)one\b(?=\W*$|\s*[,;.)]|\s+(?:anyway|too|each|regardless|automatically|though|by\s+default|"
       r"as\s+well|as\s+standard|on\s+(?:their|the|day)|from\s+it)\b)")
# And only as a plain statement about the hires: "All three get one." "..., so they each get one anyway."
# Not "you would have to request one", "nothing says they get one", "it's possible they get one".
THEY_GET = (r"(?:all\s+(?:three|3)(?:\s+of\s+them)?|all\s+of\s+them|they(?:\s+(?:all|each))?|"
            r"each(?:\s+of\s+(?:them|the\s+three))?|every(?:one|\s+(?:new\s+)?hire)|both)"
            r"(?:\s+(?:will|do|would|should)|'ll)?\s+((?:gets?|receives?|has|have)\s+)")
PLAIN_GRANT_OF_ONE = r"^\W*(?:(?:so|still|and|but|yes)\W+)?" + THEY_GET + ONE
GRANT_OF_ONE_AFTER_A_JOIN = r"(?:[,;:]\s*|\s[—–-]\s)(?:(?:so|and|but|yet|however|though|still)\s+)?" + THEY_GET + ONE
GIVEN_THING = MAILBOX_NOUN
GIVEN_STATE = (r"(?:given|provided|included|issued|provisioned|created|set\s+up|assigned|granted|allocated|allotted|"
               r"supplied|offered|available)")
NOT_GIVEN = (r"(?:\bnot\b|n't\b|\bno\b|\bnever\b|\bwithout\b|\bneither\b|\bnor\b|\bnone\b|\bnobody\b|\bno\s+one\b)"
             r"\s+(?:\w+\s+){0,4}?" + GIVE + r"\s+(?:\w+\s+){0,4}?" + GIVEN_THING +
             r"|\b" + GIVE + r"\s+no\s+(?:\w+\s+){0,2}?" + MAILBOX_NOUN +
             r"|\bno\s+(?:company\s+|corporate\s+|work\s+)?" + MAILBOX_NOUN + r"\s+(?:is|are)\s+" + GIVEN_STATE +
             r"|" + MAILBOX_NOUN + r"\s+(?:is|are)\s*(?:not|n't|never)\s+(?:\w+\s+)?" + GIVEN_STATE +
             r"|" + MAILBOX_NOUN + r"\s+(?:is|are)\s+(?:denied|refused|withheld)\b"
             r"|\b(?:denied|refused)\s+(?:a\s+)?(?:\w+\s+)?" + MAILBOX_NOUN + r"|\bno\s+" + MAILBOX_NOUN + r"\s+for\b")
IS_GIVEN = (GRANT_OF_ONE_AFTER_A_JOIN + r"|\b" + GIVE + r"\s+(?:(?!no\b|not\b|never\b)\w+\s+){0,4}?" + GIVEN_THING + r"|" + MAILBOX_NOUN +
            r"\s+(?:is|are|will\s+be|gets?)\s+(?:also\s+|always\s+)?(?:standard|" + GIVEN_STATE + r")|" +
            MAILBOX_NOUN + r"\s+comes?\s+(?:with|as)\b|"
            r"\b(?:creates?|sets?\s+up)\s+(?:a\s+)?(?:\w+\s+)?" + MAILBOX_NOUN + r"\s+for\b|"
            r"(?<!n't\s)(?<!not\s)\bexpect\w*\s+(?:a\s+)?(?:\w+\s+)?" + MAILBOX_NOUN + r"(?!\s+(?:answer|question|decision|rule))|" + MAILBOX_NOUN + r"\s+is\s+(?:theirs|yours)\b|"
            r"\b(?:but|so|and|yet|is|are)\s+yes\b|\byes\s+for\s+(?:all|each|every|both|the)\b|✅")
# Not claims about the hire: "whether they get one", "doesn't say that they get one".
# Nor is "don't assume they get one", "they may or may not get one", "who gets one".
NOT_A_CLAIM = (r"\b(?:whether|if|might|may\s+or\s+may\s+not)\b[^.,;]*|"
               r"\b(?:decid\w+|determin\w+|says?|knows?)\s+who\b[^.,;]*|"
               r"(?:n't|\bnot|\bnever|\bbefore|\bwithout)\s+(?:\w+\s+)?assum\w+[^.,;]*|"
               r"\b(?:say|says|state|states|mention|mentions|show|shows|mean|means)\s+that\b[^.,;]*")
TURN = r"\b(?:but|however|though|yet|still)\b"


def _clean(text: str) -> str:
    return text.replace("’", "'").replace("**", "").replace("`", "").lower()


def _units(answer: str) -> list[dict]:
    """Split the answer into statements. Each has the text to look for a role in, and the
    pieces to look for a mailbox answer in. A table row is one statement: its first cell is
    the label, the rest are 'Header: cell' pieces, so a cell keeps its column's meaning."""
    units, header = [], None
    for number, line in enumerate(_clean(answer).splitlines()):
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if header is None:
                header = cells
            elif not all(re.fullmatch(r":?-+:?", cell or "-") for cell in cells):
                pairs = [f"{head}: {cell}" for head, cell in zip(header, cells)]
                units.append({"label": cells[0], "role_text": " | ".join(pairs[1:]),
                              "pieces": [piece for pair in pairs[1:] for piece in _sentences(pair)]})
            continue
        header = None
        mailbox_named = False
        for sentence in re.split(r"(?<=[.!?])\s+", stripped):
            for part in _sentences(sentence):
                piece = part
                # "silent on mailboxes; all three get one regardless", or the same with a full stop:
                # "one" is the mailbox named earlier on the line.
                if mailbox_named and not re.search(MAILBOX, part):
                    piece = re.sub(PLAIN_GRANT_OF_ONE, r"they \1a mailbox", part, count=1)
                mailbox_named = mailbox_named or bool(re.search(MAILBOX, part))
                units.append({"label": part, "role_text": part, "pieces": [piece], "line": number})
    return units


def _sentences(text: str) -> list[str]:
    return [piece.strip() for piece in re.split(r"(?<=[.!?])\s+|;\s", text) if piece.strip()]


def _statements(answer: str) -> list[dict]:
    """Say which hire each statement is about.

    For a role, a statement belongs to one hire: the one whose title it names first (the label
    of a bullet or a table row), else the hire of the statement before it, as a bullet under a
    heading does. A role named in another hire's statement is never credited, so swapped roles
    score wrong. For a mailbox, a statement is about every hire it names; one that names nobody
    (a title right after a role cue is a value, not a name) is about all three if it speaks generally ("any of these roles", "no column"), else about
    the hire of the statement before it.
    """
    owner, about, units, clauses = None, set(HIRES), _units(answer), []
    for unit in units:
        first, label = {}, unit["label"]
        for key, hire in HIRES.items():
            # A title right after a role cue is a value ("Role: use Lifeguard"), not a label: it
            # must not move the line to that hire, or swapped roles under headings would score right.
            starts = [m.start() for m in re.finditer(hire["title"], label) if not re.search(ROLE_CUE, label[:m.start()])]
            if starts:
                first[key] = starts[0]
        if len(first) > 1 and unit["role_text"] is label:
            # One sentence that names several hires: each hire owns only its own clause, from its
            # title to the next hire's, so a role stated for a later hire is not credited to the first.
            cuts = sorted(first.values()) + [len(label)]
            for key, start in first.items():
                clauses.append({"role_text": label[start:cuts[cuts.index(start) + 1]], "owner": key,
                                "labelled": True, "about": set(), "pieces": []})
            unit["role_text"] = ""
        named = set(first) | ({"hospitality"} if any(
            not re.search(ROLE_CUE, label[:m.start()]) for m in re.finditer(ROLE_VALUE["hospitality"], label)) else set())
        if first:
            owner = min(first, key=first.get)
        if named:
            about = named
        unit["owner"], unit["labelled"] = owner, bool(first)
        if not named and re.search(GLOBAL, unit["label"]):
            about = set(HIRES)  # and so is what follows it, until a hire is named: "They each get one."
        unit["about"] = about
    return units + clauses


def _role_found(key: str, statements) -> str | None:
    """'stated', 'rejected' or None for the expected role, in this hire's own statements."""
    stated = rejected = False
    for index, unit in enumerate(statements):
        text = unit["role_text"]
        owned = unit["owner"] == key
        following = statements[index + 1] if index + 1 < len(statements) else {}
        taken_back = (unit.get("line") is not None and following.get("line") == unit["line"]
                      and bool(re.search(TAKEN_BACK, following["role_text"]))
                      and not re.search(OTHER_TOPIC + "|" + ABOUT_SOMETHING_ELSE + "|" + NOT_A_TAKE_BACK,
                                        following["role_text"]))
        # A rejection also counts in a line that names no hire of its own ("Do not use Lifeguard
        # for this hire"): that errs toward wrong, which is the safe side for this check.
        if not (owned or not unit["labelled"]) or text.endswith("?"):
            continue
        matches = list(re.finditer(ROLE_VALUE[key], text))
        for match in matches:
            before, after = text[:match.start()], text[match.end():]
            clause = re.split(r"[.;|\n]", after, maxsplit=1)[0]
            if re.search(REJECT_BEFORE, before) or re.search(REJECT_AFTER, after) or _negated_before(before) or (
                    _prohibited_after(clause)) or taken_back or (
                    re.search(DOUBT_AFTER, clause) and not re.search(OTHER_TOPIC, clause)):
                rejected = True
            elif not owned:
                continue
            elif re.search(ROLE_CUE, before) or re.search(HIRES[key]["title"] + AFTER_TITLE, before):
                stated = True
    return "rejected" if rejected else "stated" if stated else None


def _negated_before(before: str) -> bool:
    """True when the name follows a role cue and a negation or prohibition governs that cue."""
    if not re.search(ROLE_CUE, before):
        return False
    # Only a bare negation dangles over a comma. "The old title is invalid, map to X" does not.
    text = re.sub(r"(" + DANGLING + r")\s*,([^,]{0,40}),", r"\1 \2 ", before)
    text = re.sub(r"(" + DANGLING + r")\s*,", r"\1 ", text)
    stretch = re.split(STARTS_AGAIN, text)[-1]
    return bool(re.search(NEGATION, stretch)) and not re.search(ABOUT_THE_TITLE, stretch)


def _prohibited_after(clause: str) -> bool:
    """True when the rest of the name's clause prohibits the role itself."""
    for match in re.finditer(PROHIBIT_AFTER, clause):
        between = clause[:match.start()]
        if not (re.search(ABOUT_SOMETHING_ELSE, clause) or re.search(OTHER_TOPIC, between)
                or re.search(r"(?:\bnot|n't|\bnever)\s+(?:\w+\s+)?$", between)):
            return True
    return False


def _mailbox_value(statement: str) -> str | None:
    """'yes', 'no', 'not stated', 'mixed' or None for one sentence or table cell.

    A yes next to anything else is mixed, so "the standard does not say, but yes" is not a
    right answer. A no with a hedge is read as the hedge ("it has no mailbox entitlement for
    any role, so I can't say"), unless the sentence turns on a "but"."""
    if not re.search(MAILBOX, statement) or statement.endswith("?"):
        return None
    statement = re.sub(r"\bif\s+you\s+ask\s+me\b", " ", statement)
    claims = re.sub(NOT_A_CLAIM, " ", statement)
    unstated = bool(re.search(SAYS_NOTHING, statement) or re.search(NEITHER, statement))
    no = bool(re.search(LEADING_NO, statement) or re.search(NOT_GIVEN, claims)) and not re.search(NEITHER, statement)
    yes = bool(re.search(LEADING_YES, statement) or re.search(IS_GIVEN, re.sub(NOT_GIVEN, " ", claims)))
    if yes:
        return "mixed" if unstated or no else "yes"
    if no and unstated:
        return "mixed" if re.search(TURN, statement) else UNSTATED
    return "no" if no else UNSTATED if unstated else None


def _mailbox_found(key: str, statements) -> str | None:
    values = {value for unit in statements if key in unit["about"]
              for piece in unit["pieces"] for value in [_mailbox_value(piece)] if value}
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
            # A row whose text was withheld (measure_tc5.answer_text_may_be_saved) keeps the scores it has.
            if row.get("request") == "several lookups" and isinstance(row.get("answer"), str):
                score = score_several_lookups(row["answer"])
                row.update(facts=score["facts"], facts_right=score["facts_right"], facts_found=score["found"])
                wrong = [name for name, right in score["facts"].items() if not right]
                print(f"{path.rsplit('/', 1)[-1]}\t{row['way']}\t{score['facts_right']}/6\twrong: {wrong or 'none'}")
        if write:
            with open(path, "w") as handle:
                handle.writelines(json.dumps(row) + "\n" for row in rows)


if __name__ == "__main__":
    main(sys.argv[1:])
