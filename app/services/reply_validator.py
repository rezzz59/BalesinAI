"""Validate that composed replies follow sales-style guidelines."""
import re


_EMOJI_PATTERN = re.compile(
    "[😀😃😄😁😆😅🤣😂🙂🙃😉😊😇🥰😍🤩😘😗😙😚😋😛😜🤪😝🤑🤗🤭🤫🤔🤐😐😑😶🙄😏😒🙃😬🤥😌���😪🤤😴😷🤒🤕🤢🤮🤧🥵🥶🥴😵🤯🤠🥳😎🤓🧐😕😟🙁☹️😮😯😲😳🥺😦😧😨😰😥😢😭😱😖😣😞😓😩😫🥱😤😡😠🤬😈👿💀💩🤡👹👺👻👽👾🤖💋💯💢💥💫💦💨🕳️❤️🧡💛💚💙💜🤎🖤🤍💔❣️💕💞💓💗💘💝💟🔥⭐🌟✨🎉🎊🎈🎁🎂🙏👍👎👌🤞🤟🤘🤙👈👉👆🖕👇☝️✊👊🤛🤜👏🙌👐🤲🤝🙏✍️💅🤳💪🦾🦵🦿🦶👂🦻👃🧠🦷🦴👀👁️👅👄💋]"
)


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
    """Detect when the reply asks about something already mentioned in user message."""
    if not user_message:
        return []
    reply_lower = reply.lower()
    user_lower = user_message.lower()

    violations = []
    # Common attribute-asking patterns
    if "ukuran" in user_lower and "ukuran" in reply_lower:
        violations.append("asked about size already mentioned in user message")
    if "warna" in user_lower and "warna" in reply_lower:
        violations.append("asked about color already mentioned in user message")
    if "size" in user_lower and "size" in reply_lower:
        violations.append("asked about size already mentioned in user message")
    return violations


def _count_questions(text: str) -> int:
    """Number of question marks (the guiding question the reply ends with)."""
    return text.count("?") + text.count("؟")


def _ends_with_question(text: str) -> bool:
    """True if the reply ends with a guiding question (ignoring trailing emoji/spaces)."""
    t = text.strip()
    while t:
        if t[-1] in {"?", "؟"}:
            return True
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