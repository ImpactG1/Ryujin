import logging
import re
import sys
from typing import Any, Dict

EMAIL_REGEX = re.compile(r"([a-zA-Z0-9_.+-]+)@([a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)")
TOKEN_REGEX = re.compile(r"(Bearer\s+[A-Za-z0-9\-_.]+|gsk_[A-Za-z0-9]{20,}|(?:token|secret|password)\s*[:=]\s*['\"]?[^\s'\"&]+['\"]?)", re.IGNORECASE)
PHONE_REGEX = re.compile(r"(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}")


def mask_pii_string(text: str) -> str:
    """Mask email addresses, tokens/secrets, and phone numbers from a string."""
    if not isinstance(text, str):
        return text

    def mask_email(match):
        user, domain = match.group(1), match.group(2)
        if len(user) <= 2:
            masked_user = user[0] + "*"
        else:
            masked_user = user[0] + "*" * (len(user) - 2) + user[-1]
        return f"{masked_user}@{domain}"

    text = EMAIL_REGEX.sub(mask_email, text)
    text = TOKEN_REGEX.sub("[REDACTED_SECRET]", text)
    text = PHONE_REGEX.sub("[REDACTED_PHONE]", text)
    return text


def mask_pii_dict(data: Dict[str, Any], is_admin: bool = False) -> Dict[str, Any]:
    """
    Mask sensitive fields in dictionaries.
    If is_admin is True, keep non-secret PII; if False, mask email/phone/full_name.
    Secrets and tokens are ALWAYS masked.
    """
    masked = {}
    for key, value in data.items():
        lower_key = key.lower()
        if any(secret_term in lower_key for secret_term in ["token", "secret", "password", "api_key"]):
            masked[key] = "********"
        elif not is_admin:
            if any(name_term in lower_key for name_term in ["full_name", "name"]):
                if isinstance(value, str) and len(value) > 0:
                    masked[key] = f"{value[0]}***"
                else:
                    masked[key] = "[PROTECTED_PII]"
            elif isinstance(value, str):
                masked[key] = mask_pii_string(value)
            elif isinstance(value, dict):
                masked[key] = mask_pii_dict(value, is_admin=False)
            elif isinstance(value, list):
                masked[key] = [
                    mask_pii_dict(item, is_admin=False) if isinstance(item, dict)
                    else (mask_pii_string(item) if isinstance(item, str) else item)
                    for item in value
                ]
            else:
                masked[key] = value
        else:
            if isinstance(value, dict):
                masked[key] = mask_pii_dict(value, is_admin=True)
            elif isinstance(value, list):
                masked[key] = [
                    mask_pii_dict(item, is_admin=True) if isinstance(item, dict)
                    else item
                    for item in value
                ]
            else:
                masked[key] = value
    return masked


class PIIMaskingFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        orig = super().format(record)
        return mask_pii_string(orig)


def setup_logger(name: str = "ryujin", level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        formatter = PIIMaskingFormatter(
            fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    return logger


logger = setup_logger()
