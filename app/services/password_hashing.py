from pwdlib import PasswordHash


_password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    if not password:
        raise ValueError("Password is required")
    return _password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    return _password_hash.verify(password, encoded_hash)
