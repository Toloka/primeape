import json
import re
import unicodedata
from criterion_parser import CRITERIA, LABELS, unique_object

MAX_RESPONSE_LEN = 10_000


def clean(text):
    text = (
        unicodedata.normalize("NFC", text).replace("\u200e", "").replace("\u200f", "")
    )
    return text.replace("*", "").replace("`", "").strip()


def label_key(text):
    text = clean(text).casefold()
    text = re.sub(r"^\s*(?:[-•>#]\s*)*(?:\d+[.)]\s*)?", "", text)
    # Some outputs repeat the criterion's parenthesized definition from P1.
    text = re.sub(r"\s+\([^()]*\)\s*$", "", text)
    return " ".join(text.strip().split())


# Additional aliases come from the repository's actual P0/P1/P2 templates.
EXTRA_LABELS = {
    "relevance": [
        "प्रासंगिकता",
        "مطابقت کی ترجیح",
        "Preferencia de relevancia",
        "Ààyò ìbáṣepọ̀",
    ],
    "naturalness": [
        "स्वाभाविकता",
        "قدرتی انداز کی ترجیح",
        "Preferencia de naturalidad",
        "Ààyò ìmọ̀lára adayeba",
    ],
    "truthfulness": [
        "सत्यता",
        "سچائی کی ترجیح",
        "Preferencia de veracidad",
        "Ààyò òtítọ́",
        "Sannhet",
    ],
    "safety": [
        "सुरक्षा",
        "حفاظت کی ترجیح",
        "Preferencia de seguridad",
        "Ààyò ààbò",
        "Sikkerheit",
    ],
    "overall_quality": [
        "समग्र",
        "समग्र गुणवत्ता",
        "مجموعی معیار کی ترجیح",
        "Preferencia de calidad general",
        "Sammenlagt Kvalitet",
        "Ààyò didara lapapọ̀",
    ],
}
# English renderings of the Hindi "<criterion> वरीयता" labels that judges produce.
for _c, _names in {
    "relevance": ["relevance"],
    "naturalness": ["naturalness"],
    "truthfulness": ["truthfulness"],
    "safety": ["safety"],
    "overall_quality": ["overall quality", "overall"],
}.items():
    EXTRA_LABELS[_c] += [f"{n} priority" for n in _names]
ALIASES = {
    label_key(label): c for c in CRITERIA for label in [c, *LABELS[c], *EXTRA_LABELS[c]]
}
VALUES = {
    "a": "A",
    "b": "B",
    **dict.fromkeys(
        [
            "tie",
            "ties",
            "tied",
            "equal",
            "draw",
            "same",
            "égalité",
            "egalite",
            "empate",
            "uavgjort",
            "बराबर",
            "ìdọ́gba",
            "idogba",
            # Hindi tie expressions judges wrote instead of "Tie" (the Hindi explanation
            # prompts omit the option): tie, equal, both equal, no preference
            "टाई",
            "समान",
            "दोनों समान",
            "दोनों बराबर",
            "दोनों बराबर हैं",
            "दोनों समान हैं",
            "दोनों उत्तर बराबर हैं",
            "दोनों उत्तर समान हैं",
            "कोई वरीयता नहीं",
        ],
        "tie",
    ),
    # Hindi spellings of the letters A and B
    "ए": "A",
    "बी": "B",
    "ब": "B",
}
# Explicit selected-answer prefixes used in the prompts; never arbitrary filler.
_PREFIX_WORDS = [
    "response",
    "answer",
    "option",
    "réponse",
    "respuesta",
    "svar",
    "ìdáhùn",
    "उत्तर",
    "विकल्प",
    "جواب",
    "चुना गया उत्तर",
    "चयनित उत्तर",
    "réponse sélectionnée",
    "respuesta seleccionada",
    "selected response",
    "valgt svar",
    "منتخب جواب",
]
# longest first, so "réponse sélectionnée : B" is not cut after "réponse"
PREFIX = re.compile(
    r"^(?:" + "|".join(sorted(_PREFIX_WORDS, key=len, reverse=True)) + r")\s*[:：]?\s+",
    re.I,
)
CHECK_MARKS = re.compile("[\u2705\u2714\u2713\u2611\ufe0f]")
COMPARISON = re.compile(r"^(A|B)\s*(>|=)\s*(A|B)$", re.I)
SINGLE_LABELS = {
    label_key(s)
    for s in [
        "Answer",
        "Response",
        "Verdict",
        "Final verdict",
        "Final answer",
        "Winner",
        "Réponse",
        "Réponse sélectionnée",
        "La réponse est",
        "Verdict final",
        "Respuesta",
        "Respuesta seleccionada",
        "Svar",
        "Valgt svar",
        "उत्तर",
        "चुना गया उत्तर",
        "चयनित उत्तर",
        "अंतिम निर्णय",
        "جواب",
        "منتخب جواب",
        "حتمی فیصلہ",
        "Ìdáhùn",
        "Dáhùn",
        "Ìpinnu",
        "Ìdáhùn tí o yàn",
        "Ìdáhùn tí mo yàn",
    ]
}


def fold(key):
    """label_key without diacritics, for answer-word labels only."""
    return "".join(
        ch for ch in unicodedata.normalize("NFD", key) if not unicodedata.combining(ch)
    )


SINGLE_LABELS_FOLDED = {fold(s) for s in SINGLE_LABELS}
# "A/B/Tie:" or "(A/B):" echoed from the template before the actual answer
OPTION_LIST = re.compile(
    r"^\(?\s*A\s*/\s*B(?:\s*/\s*[^\s:：)]+)?\s*\)?\s*[:：]\s*", re.I
)
# the template's answer placeholder left after a filled-in verdict
PLACEHOLDER_SUFFIX = re.compile(
    r"\s*[-–—(]?\s*(?:चुना गया उत्तर|चयनित उत्तर|selected response|selected answer|chosen answer|"
    r"réponse sélectionnée|respuesta seleccionada|valgt svar|منتخب جواب|ìdáhùn tí o yàn|"
    r"चुना गया|sélectionnée|seleccionada|selected|chosen)\s*\)?\s*$",
    re.I,
)


def _decision_attempt(raw):
    """Distinguish an invalid decision field from an ordinary prose rationale.

    Prose-only labelled explanations (more than four words) cannot erase a
    preceding explicit verdict, even when they start with "Response A ...".
    Short placeholders and ambiguous choices still invalidate that slot.
    """
    raw = clean(raw).strip(" _\"'‘’“”")
    return len(raw.split()) <= 4


def value(text, allow_inline=True):
    """A whole verdict, optionally followed by a delimited inline rationale.

    Accept 'B — explanation', not 'A is less safe than B' or 'A / B'.
    Both/neither are not assumed to be ties when they introduce ordinary prose.
    """
    text = CHECK_MARKS.sub("", clean(text)).strip(" _\"'‘’“”")
    for _ in range(3):  # "Overall: Answer: A", "चुना गया उत्तर: उत्तर B"
        before = text
        label = re.match(r"^([^:：]{1,40})[:：]\s*(.+)$", text)
        if label and ALIASES.get(label_key(label[1])) is not None:
            text = label[2]
        text = OPTION_LIST.sub("", text).strip(" _\"'‘’“”")
        text = PREFIX.sub("", text).strip(" _\"'‘’“”")
        if text == before:
            break
    whole = text.rstrip(".।,;! ").strip(" _\"'‘’“”")
    if whole.casefold() in VALUES:
        return VALUES[whole.casefold()]
    filled = PLACEHOLDER_SUFFIX.sub("", whole).rstrip(".।,;! ").strip(" _\"'‘’“”")
    if filled != whole and filled.casefold() in VALUES:
        return VALUES[filled.casefold()]
    cmp = COMPARISON.match(whole)
    if cmp and cmp[1].upper() != cmp[3].upper():
        return "tie" if cmp[2] == "=" else cmp[1].upper()
    if allow_inline:
        # Delimited verdict tokens only. A dash is required to have whitespace
        # before it, so A-B (an alternative/range) is not accepted as A.
        match = re.match(r"^(.+?)(?:\s+[—–-]\s+|\s*:\s+|\s+\()(.*)$", text)
        if match:
            rest = match[2].strip().rstrip(")").strip()
            first = value(match[1], allow_inline=False)
            if first is not None and value(rest, allow_inline=False) == first:
                return first  # "A (Ìdáhùn A)": a restatement, not an alternative
            if value(rest, allow_inline=False) is not None or re.match(
                r"^(?:or|and|ou|o|eller|या|یا|tàbí)\s+(?:A|B|Tie)\b", rest, re.I
            ):
                return None
            return value(match[1], allow_inline=False)
    return None


def _closing_label(line):
    """'<prose>. <criterion label>: <verdict>' at the end of a line -> (criterion, verdict).

    Only the last colon is used, the label must directly precede it (one to four
    words after the last sentence boundary), and the value must be a whole verdict.
    """
    head, sep, tail = clean(line).rpartition(":")
    if not sep or value(tail, False) is None:
        return None, None
    head = re.split(r"[.!?।۔]\s+", head)[-1]
    words = head.split()
    for n in range(1, min(4, len(words)) + 1):
        c = ALIASES.get(label_key(" ".join(words[-n:])))
        if c is not None:
            return c, tail
    return None, None


def _section_verdict(lines, start):
    """Verdict stated inside a criterion section whose heading had no value.

    Scans from `start` to the next labelled criterion line for
    'Answer/Verdict/Ìdáhùn: X' fields and standalone verdict lines. Returns
    (raw verdict text, end line) if they all agree; conflicting answers return
    ("", end) so the slot abstains; no answer returns None.
    """
    found = []
    for i in range(start, len(lines)):
        parts = re.split("[:：]", lines[i], maxsplit=1)
        if len(parts) == 2 and ALIASES.get(label_key(parts[0])) is not None:
            break
        raw = (
            parts[1]
            if len(parts) == 2 and fold(label_key(parts[0])) in SINGLE_LABELS_FOLDED
            else lines[i]
        )
        if value(raw, False) is not None:
            found.append((value(raw, False), raw, i))
    if not found:
        return None
    _, raw, i = found[-1]
    if len({v for v, _, _ in found}) > 1:
        return "", i + 1
    return raw, i + 1


def _result(criteria):
    return {
        "predicted": dict.fromkeys(criteria),
        "status": dict.fromkeys(criteria, "missing"),
        "evidence": {c: [] for c in criteria},
    }


def parse(text, criterion=None):
    """Parse combined output or one explicitly requested criterion.

    Separated outputs may also use a standalone verdict on the final line.
    Missing/ambiguous named final fields cannot fall back to earlier decisions.
    """
    if criterion is not None and criterion not in CRITERIA:
        raise ValueError("unknown criterion: " + criterion)
    criteria = CRITERIA if criterion is None else (criterion,)
    result = _result(criteria)
    if not isinstance(text, str) or not text.strip():
        result["status"] = dict.fromkeys(criteria, "empty_or_nontext")
        return result
    if len(text) > MAX_RESPONSE_LEN:
        result["status"] = dict.fromkeys(criteria, "over_length_limit")
        return result
    text = text.strip()
    if text.startswith("```") and text.splitlines()[-1].strip() == "```":
        text = "\n".join(text.splitlines()[1:-1]).strip()
    occurrences = {c: [] for c in criteria}
    if text.startswith(("{", "[")):
        try:
            data = json.loads(text, object_pairs_hook=unique_object)
            if not isinstance(data, dict):
                raise ValueError("expected JSON object")
            fields = data.get("verdicts", data)
            if not isinstance(fields, dict):
                raise ValueError("expected verdicts object")
            for c in criteria:
                if c in fields:
                    raw = fields[c]
                    occurrences[c].append(
                        value(raw, False) if isinstance(raw, str) else None
                    )
                    result["evidence"][c].append({"json_key": c, "raw_value": raw})
        except (ValueError, TypeError):
            result["status"] = dict.fromkeys(criteria, "invalid_json")
            return result
    else:
        lines = text.splitlines()
        last_nonempty = max(i for i, line in enumerate(lines) if line.strip())
        named_at_last = False
        for index, line in enumerate(lines):
            parts = re.split("[:：]", line, maxsplit=1)
            if len(parts) != 2:
                continue
            key = label_key(parts[0])
            c = ALIASES.get(key)
            if c is None and criterion is not None and key in SINGLE_LABELS:
                c = criterion
            elif (
                c is None
                and criterion is not None
                and fold(key) in SINGLE_LABELS_FOLDED
                and value(parts[1]) is not None
            ):
                c = criterion  # diacritic variant: may add a verdict, never erase one
            if c is None:
                c, tail = _closing_label(line)
                if c is not None:
                    parts = [line, tail]
            if c is None:
                continue
            if index == last_nonempty:
                named_at_last = True
            if c not in criteria:
                continue
            raw = clean(parts[1])
            end = index + 1
            if not raw:
                following = index + 1
                while following < len(lines) and not lines[following].strip():
                    following += 1
                # A heading may introduce the verdict on the next nonempty line or
                # state it inside its section; conflicting answers there abstain.
                found = _section_verdict(lines, following)
                if found is not None:
                    raw, end = found
                else:
                    # Empty headers are recorded too: an incomplete final field
                    # must not reuse an earlier decision for this criterion.
                    raw = ""
            verdict = value(raw)
            if verdict is not None or _decision_attempt(raw):
                occurrences[c].append(verdict)
            result["evidence"][c].append(
                {
                    "line": index + 1,
                    "end_line": end,
                    "text": "\n".join(lines[index:end]),
                }
            )
        if criterion is not None and not named_at_last:
            final = value(lines[last_nonempty], False)
            if final is not None:
                occurrences[criterion].append(final)
                result["evidence"][criterion].append(
                    {"line": last_nonempty + 1, "text": lines[last_nonempty]}
                )
            elif occurrences[criterion] and re.fullmatch(
                r"[ABabTtIiEe /|,]+", clean(lines[last_nonempty])
            ):
                occurrences[criterion].append(None)
                result["evidence"][criterion].append(
                    {"line": last_nonempty + 1, "text": lines[last_nonempty]}
                )
    for c, vals in occurrences.items():
        explicit = {v for v in vals if v is not None}
        if len(explicit) > 1:
            result["status"][c] = "conflicting_verdicts"
        elif vals and vals[-1] is None:
            result["status"][c] = "unparseable_value"
        elif explicit:
            result["predicted"][c] = next(iter(explicit))
            result["status"][c] = "valid"
    return result
