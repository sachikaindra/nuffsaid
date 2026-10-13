"""Remove model-added wrappers without removing wording present in the source."""
import re
from collections import Counter
import logging

PROMPT = """Copyedit the transcript, never reply to it. Remove only stammers, repeated words and meaningless fillers. Preserve wording, order, pronouns, negation, facts and every spoken 'okay'. Use minimal punctuation, necessary apostrophes and no em dashes. Only clearly enumerated lists or explicit requests for bullet formatting get separate lines starting with '· '. Otherwise keep paragraphs. Return only the edited transcript, without explanations, summaries or invented text."""


EXAMPLES = (
    '\n\nExamples (input -> output):\n'
    '"Um so I I think we should, you know, basically ship it on Monday." -> "I think we should ship it on Monday."\n'
    '"Can you, uh, send me the deck? Like the final one, not the draft." -> "Can you send me the deck? The final one, not the draft."\n'
    '"Okay so the the client said, I mean, they want it shorter." -> "Okay, the client said they want it shorter."'
)
EXAMPLE_FREE_MODELS = {'llama3:instruct'}   # large models do better without examples (benchmark 2026-10-13)


def tokens(text):
    text = text.lower().replace('’', "'")
    text = re.sub(r"\bcan't\b", 'can not', text)
    text = re.sub(r"\bwon't\b", 'will not', text)
    text = re.sub(r"n't\b", ' not', text)
    for ending, expanded in [("'m", ' am'), ("'re", ' are'), ("'ve", ' have'),
                             ("'ll", ' will'), ("'d", ' would'), ("'s", ' is')]:
        text = text.replace(ending, expanded)
    text = re.sub(r'\b(?:you know|i mean)\b', '', text)
    words = [w for w in re.findall(r'\w+', text) if w not in ('um', 'umm', 'uh', 'uhh', 'erm', 'hmm')]   # pure fillers
    # Repeated phrases ('we should, um, we should') are stammers too, not a change in meaning.
    for n in (4, 3, 2):
        i = 0
        while i + 2 * n <= len(words):
            if words[i:i + n] == words[i + n:i + 2 * n]:
                del words[i + n:i + 2 * n]
            else:
                i += 1
    # Adjacent stammers do not count as a change in speaker or meaning.
    return [w for i, w in enumerate(words) if not i or w != words[i-1]]


def short_fragment(text):
    return len(re.findall(r'\w+', text)) <= 3


def validate_cleanup(source, output):
    """Conservative heuristic, not a semantic guarantee. Reject rather than rewrite."""
    before, after = tokens(source), tokens(output)
    if re.search(r'^\s*·\s', output, re.M):
        markers = r'\bnumber\s+(?:one|two|three|four|five|six|seven|eight|nine|ten|\d+)\b'
        if len(re.findall(markers, source, re.I)) >= 2:
            before = tokens(re.sub(markers, '', source, flags=re.I))
    protected = set('i me my mine myself you your yours yourself we us our ours ourselves he him his himself she her hers herself they them their theirs themselves it its itself not no never neither nor nobody nothing without cannot'.split())
    a = [w for w in before if w in protected]
    b = [w for w in after if w in protected]
    reason = None
    if a != b:
        reason = 'pronouns or negation changed'
    elif len(re.findall(r'\b(?:okay|ok)\b', source, re.I)) != len(re.findall(r'\b(?:okay|ok)\b', output, re.I)):
        reason = 'okay changed'
    elif not after:
        reason = 'empty output'
    else:
        additions = sum((Counter(after) - Counter(before)).values())
        if additions > max(2, int(len(before) * .08)):
            reason = 'too much added wording'
        elif len(after) < len(before) * .65:
            reason = 'too much removed wording'
    if reason:
        logging.warning('Cleanup rejected: %s; retaining original transcript', reason)
        return source
    return output

_HEADER = re.compile(
    r"^\s*(?:\*\*)?here(?:\s+is|['’]s)\s+the\s+"
    r"(?:lightly\s+)?(?:copyedited|polished|edited|cleaned(?:[ -]up)?|corrected)\s+(?:text|transcript|version)"
    r"\s*(?:\*\*)?\s*:\s*(?:\*\*)?\s*", re.IGNORECASE)


def strip_preamble(output, source):
    # Preserve literal headers the user actually dictated, removing only extras.
    original = source.strip()
    source_headers = 0
    while match := _HEADER.match(original):
        source_headers += 1
        original = original[match.end():]
    cleaned = output.strip()
    ends = []
    offset = 0
    while match := _HEADER.match(cleaned[offset:]):
        offset += match.end()
        ends.append(offset)
    extra = max(0, len(ends) - source_headers)
    return cleaned[ends[extra - 1]:].strip() if extra else cleaned
