"""Validate that composed replies follow sales-style guidelines."""
import re


_EMOJI_PATTERN = re.compile(
    "[😀😃😄😁😆😅🤣😂🙂🙃😉😊😇🥰😍🤩😘😗😙😚😋😛😜🤪😝🤑🤗🤭🤫🤔🤐😐😑😶🙄😏😒🙃😬🤥😌😴😪🤤😷🤒🤕🤢🤮🤧🥵🥶🥴😵🤯🤠🥳😎🤓🧐😕😟🙁☹️😮😯😲😳🥺😦😧😨😰😥😢😭😱😖😣😞😓😩😫🥱😤😡😠🤬😈👿💀💩🤡👹👺👻👽👾🤖💋💯💢💥💫💦💨🕳️❤️🧡💛💚💙💜🤎🖤🤍💔❣️💕💞💓💗💘💝💟🔥⭐🌟✨🎉🎊🎈🎁🎂🙏👍👎👌🤞🤟🤘🤙👈👉👆🖕👇☝️✊👊🤛🤜👏🙌👐🤲🤝✍️💅🤳💪🦾🦵🦿🦶👂🦻👃🧠🦷🦴👀👁️👅👄]"
)

# Non-Indonesian scripts that must never appear in a reply (LLMs occasionally
# leak CJK/Arabic when translating a source row).
_NON_LATIN = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\u0600-\u06ff]")


def _count_sentences(text: str) -> int:
    """Rough sentence count by splitting on period, exclamation, question mark."""
    text = text.strip()
    if not text:
        return 0
    parts = re.split(r"[.!?]+", text)
    return len([p for p in parts if p.strip()])


def _count_emojis(text: str) -> int:
    return len(_EMOJI_PATTERN.findall(text))


def _listener_violations(reply: str, user_message: str = "") -> list:
    """Detect when the reply RE-ASKS an already-mentioned attribute.

    Only an OPEN question that asks the buyer to specify an attribute they
    already named (e.g. "mau ukuran apa?") is a violation. Confirming the
    exact chosen variant ("mau kami amankan stock size L navy?") or stating
    the attribute while answering ("tersedia warna navy dan hitam") is
    legitimate. 'ukuran'/'size' count as one attribute family.
    """
    if not user_message:
        return []
    reply_lower = reply.lower()
    user_lower = user_message.lower()

    _ATTR_SYNONYMS = {"size": ("ukuran", "size"), "warna": ("warna",)}
    mentioned = {
        fam for fam, words in _ATTR_SYNONYMS.items()
        if any(w in user_lower for w in words)
    }
    if not mentioned:
        return []

    open_q = re.compile(r"\b(apa|gimana|bagaimana|mana|berapa)\b")
    violations = set()
    for m in re.finditer(r"[^.!?]*\?", reply_lower):
        sentence = m.group(0)
        if not open_q.search(sentence):
            continue
        for fam in mentioned:
            if any(w in sentence for w in _ATTR_SYNONYMS[fam]):
                violations.add(f"asked about {fam} already mentioned in user message")
    return sorted(violations)


def _count_questions(text: str) -> int:
    """Number of question marks (the guiding question the reply ends with)."""
    return text.count("?") + text.count("؟")


def _ends_with_question(text: str) -> bool:
    """True if the reply ends with a guiding question (ignoring trailing
    emoji/spaces/punctuation and a trailing parenthetical like "(size chart...)").
    """
    t = text.strip()
    while t:
        if t[-1] in {"?", "؟"}:
            return True
        if t[-1] == ")":
            # Strip a trailing parenthetical: "ukuran apa? (size chart M..)"
            open_idx = t.rfind("(")
            if open_idx != -1:
                t = t[:open_idx].rstrip()
                continue
        if t[-1].isspace() or t[-1] in {".", ",", "!", ":"} or _EMOJI_PATTERN.findall(t[-1]):
            t = t[:-1].strip()
            continue
        return False
    return False


def validate_sales_style(reply_text: str, user_message: str = "") -> tuple:
    """Returns (is_valid, violation_message).

    Rules:
      - max 6 sentences
      - max 2 emojis
      - exactly 1 guiding question, at the end (anti-ghosting, no decision fatigue)
      - don't ask about attributes customer already mentioned
    """
    violations = []

    if _NON_LATIN.search(reply_text):
        violations.append("reply contains non-Indonesian script (e.g. Mandarin/Arabic)")

    n_sent = _count_sentences(reply_text)
    if n_sent > 6:
        violations.append(f"response exceeds 6 sentences ({n_sent})")

    n_emo = _count_emojis(reply_text)
    if n_emo > 2:
        violations.append(f"more than 2 emojis ({n_emo})")

    if not _ends_with_question(reply_text):
        violations.append("reply does not end with a guiding question")

    n_q = _count_questions(reply_text)
    if n_q > 1:
        violations.append(f"more than 1 question ({n_q})")

    listener_v = _listener_violations(reply_text, user_message)
    if listener_v:
        violations.append("listener rule violated: " + "; ".join(listener_v))

    if violations:
        return False, "; ".join(violations)
    return True, "OK"