"""비밀번호 해싱 — 외부 의존 없이 stdlib pbkdf2_hmac 사용 (Phase 1).

저장 포맷: ``pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>``
- salt 는 요청마다 랜덤 (``secrets.token_bytes``).
- 검증은 ``secrets.compare_digest`` 로 상수시간 비교.
- 어떤 평문과도 일치하지 않는 sentinel(``disabled$...``)은 verify 가 항상 False 를 반환한다
  (마이그레이션 백필로 로그인 불가 상태를 표현).
"""

from __future__ import annotations

import base64
import hashlib
import secrets

_ALGORITHM = "pbkdf2_sha256"
_ITERATIONS = 200_000
_SALT_BYTES = 16


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(plain: str, *, iterations: int = _ITERATIONS) -> str:
    """평문 비밀번호 → 저장 가능한 해시 문자열."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations)
    return f"{_ALGORITHM}${iterations}${_b64(salt)}${_b64(digest)}"


def verify_password(plain: str, stored: str) -> bool:
    """평문이 저장된 해시와 일치하는지 — 형식 오류/sentinel 은 모두 False."""
    try:
        algorithm, iter_str, salt_b64, hash_b64 = stored.split("$")
    except ValueError:
        return False
    if algorithm != _ALGORITHM:
        return False
    try:
        iterations = int(iter_str)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, TypeError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations)
    return secrets.compare_digest(digest, expected)
