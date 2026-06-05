import os
from cryptography.fernet import Fernet, InvalidToken

_raw_key = os.getenv("ENCRYPTION_KEY", "").strip().encode()


def _fernet():
    if not _raw_key:
        return None
    try:
        return Fernet(_raw_key)
    except Exception:
        return None


def encrypt(text: str) -> str:
    f = _fernet()
    if not f or not text:
        return text
    return f.encrypt(text.encode()).decode()


def decrypt(text: str) -> str:
    f = _fernet()
    if not f or not text:
        return text
    try:
        return f.decrypt(text.encode()).decode()
    except (InvalidToken, Exception):
        return text  # 암호화 전 저장된 값은 그대로 반환
