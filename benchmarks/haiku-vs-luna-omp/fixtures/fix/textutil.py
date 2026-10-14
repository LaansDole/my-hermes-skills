"""Small text helpers. Several functions are buggy; tests in test_textutil.py define the spec."""
import re
import unicodedata


def slugify(s):
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s


def wrap(text, width):
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        if len(cur) + len(w) > width:
            lines.append(cur)
            cur = w
        else:
            cur = cur + " " + w
    lines.append(cur)
    return lines


def parse_duration(s):
    """'1h30m', '45s', '2h' -> seconds."""
    total = 0
    for num, unit in re.findall(r"(\d+)([hms])", s):
        total += int(num) * {"h": 3600, "m": 60, "s": 1}[unit]
    return total
