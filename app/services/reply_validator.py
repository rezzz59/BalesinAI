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


def validate_sales_style(reply_text: str, user_message: str = "") -> tuple:
    """Returns (is_valid, violation_message).

    Rules:
      - max 3 sentences
      - max 1 emoji
      - don't ask about attributes customer already mentioned
    """
    violations = []

    n_sent = _count_sentences(reply_text)
    if n_sent > 3:
        violations.append(f"response exceeds 3 sentences ({n_sent})")

    n_emo = _count_emojis(reply_text)
    if n_emo > 1:
        violations.append(f"more than 1 emoji ({n_emo})")

    listener_v = _listener_violations(reply_text, user_message)
    if listener_v:
        violations.append("listener rule violated: " + "; ".join(listener_v))

    if violations:
        return False, "; ".join(violations)
    return True, "OK"