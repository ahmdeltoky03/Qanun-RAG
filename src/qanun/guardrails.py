"""Input and output guardrails (rule based, fast, no extra model needed)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from qanun.arabic import to_western_digits

_INJECTION = [
    r"ignore (all |any |the )?(previous|prior|above) (instructions|prompts?)",
    r"disregard (all |any |the )?(previous|prior|above)",
    r"(reveal|show|print|repeat) (me )?(your|the) (system )?(prompt|instructions)",
    r"you are now\b", r"\bjailbreak\b", r"\bDAN mode\b", r"act as (?:an? )?(?:unrestricted|different)",
    r"تجاهل (كل |جميع )?(التعليمات|الأوامر)( السابقة)?", r"انس[ىي] (كل |جميع )?(التعليمات|الأوامر)",
    r"(اكشف|اعرض|اطبع|كرر) (لي )?(التعليمات|البرومبت|الموجه)", r"أنت الآن",
]  # fmt: skip
_INJECTION_RE = re.compile("|".join(_INJECTION), re.I)
_PII = {
    "national_id": re.compile(r"(?<!\d)[23]\d{13}(?!\d)"),
    "phone": re.compile(r"(?<!\d)(?:\+?20|0)1[0125]\d{8}(?!\d)"),
    "email": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    "card": re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"),
}
_CITE = re.compile(r"\[(?:المادة|Article)\s*(\d{1,4})\]")


MESSAGES = {
    "empty": ("السؤال فارغ.", "Question is empty."),
    "too_long": ("السؤال أطول من الحد المسموح.", "Question exceeds the maximum length."),
    "prompt_injection": ("يبدو أن الطلب يحاول تغيير تعليمات المساعد.", "This looks like an attempt to override the assistant's instructions."),
    "pii": ("يرجى حذف البيانات الشخصية (رقم قومي، هاتف، بريد، بطاقة) من السؤال.", "Please remove personal data (ID, phone, email, card) from the question."),
}  # fmt: skip


class GuardrailViolation(Exception):
    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code, self.message = code, message or MESSAGES.get(code, ("", code))[1]

    def localized(self, arabic: bool) -> str:
        ar, en = MESSAGES.get(self.code, ("", self.message))
        return ar if arabic and ar else en


@dataclass
class InputCheck:
    question: str
    flags: list[str] = field(default_factory=list)


def _luhn(digits: str) -> bool:
    d = [int(c) for c in digits][::-1]
    return (sum(d[0::2]) + sum(sum(divmod(2 * x, 10)) for x in d[1::2])) % 10 == 0


def check_input(question: str, max_chars: int = 1000, pii_mode: str = "mask") -> InputCheck:
    q = question.strip()
    if not q:
        raise GuardrailViolation("empty", "Question is empty.")
    if len(q) > max_chars:
        raise GuardrailViolation("too_long", f"Question exceeds {max_chars} characters.")
    if _INJECTION_RE.search(q):
        raise GuardrailViolation(
            "prompt_injection", "This looks like an attempt to override the assistant's instructions."
        )
    flags: list[str] = []
    if pii_mode != "off":
        ascii_q = to_western_digits(q)
        for kind, rx in _PII.items():
            for m in list(rx.finditer(ascii_q)):
                if kind == "card" and not _luhn(re.sub(r"\D", "", m.group())):
                    continue
                flags.append(f"pii:{kind}")
        if flags:
            if pii_mode == "block":
                raise GuardrailViolation(
                    "pii", "Please remove personal data (ID, phone, email, card) from the question."
                )
            # remove the personal data entirely: it carries no legal meaning and would only pollute retrieval
            for kind, rx in _PII.items():
                ascii_q = (
                    rx.sub(" ", ascii_q)
                    if kind != "card"
                    else re.sub(rx, lambda m: " " if _luhn(re.sub(r"\D", "", m.group())) else m.group(), ascii_q)
                )
            q = re.sub(r"\s+", " ", ascii_q).strip()
    return InputCheck(q, sorted(set(flags)))


def cited_articles(answer: str) -> list[int]:
    return [int(n) for n in _CITE.findall(answer)]


def check_output(answer: str, allowed: set[int]) -> tuple[str, list[str]]:
    """Drop citations that do not point at a retrieved article (ungrounded) and flag them."""
    flags: list[str] = []

    def repl(m: re.Match) -> str:
        if int(m.group(1)) in allowed:
            return m.group(0)
        flags.append(f"ungrounded_citation:{m.group(1)}")
        return ""

    cleaned = re.sub(r"\s+", " ", _CITE.sub(repl, answer)).strip()
    return cleaned, flags
