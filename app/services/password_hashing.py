from pwdlib import PasswordHash


_password_hash = PasswordHash.recommended()
_dummy_hash = _password_hash.hash("dummy password used for constant-time verification")


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password is required")
    return _password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    return _password_hash.verify(password, encoded_hash)


def verify_password_or_dummy(password: str, encoded_hash: str | None) -> bool:
    return _password_hash.verify(password, encoded_hash or _dummy_hash)
