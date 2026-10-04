"""Run inside the API container against the real API, database and worker."""
import argparse
from http.cookiejar import CookieJar
import json
from pathlib import Path
import secrets
import sys
import time
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

from app.core.database import create_session
from app.crud.user import create_user
from app.services.password_hashing import hash_password

EXPECTED_TEXT = "Novad smoke test confirms document processing works."


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--database-outage", action="store_true")
    args = parser.parse_args()
    opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def request(path: str, data=None, content_type="application/json"):
        response = opener.open(Request(
            "http://127.0.0.1:8000" + path,
            data=data,
            headers={"Content-Type": content_type},
        ), timeout=5)
        with response:
            return json.load(response)

    if args.database_outage:
        assert request("/health")["status"] == "ok"
        try:
            request("/ready")
        except HTTPError as error:
            assert error.code == 503, error.code
        else:
            raise AssertionError("/ready passed without the database")
        print("PASS: database outage gives /ready=503, /health=200", flush=True)
        return

    username = "smoke-" + secrets.token_hex(8)
    password = secrets.token_urlsafe(24)
    with create_session() as db:
        create_user(db, username=username, password_hash=hash_password(password))

    request("/api/auth/login", json.dumps({
        "username": username, "password": password,
    }).encode())
    boundary = "novad-smoke-" + secrets.token_hex(16)
    pdf = Path(__file__).with_name("sample.pdf").read_bytes()
    body = (
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
        'filename="sample.pdf"\r\nContent-Type: application/pdf\r\n\r\n'
    ).encode() + pdf + f"\r\n--{boundary}--\r\n".encode()
    document = request("/api/documents/upload", body, f"multipart/form-data; boundary={boundary}")
    deadline = time.monotonic() + args.timeout
    while document["status"] != "processed":
        if document["status"] == "failed":
            raise RuntimeError(f"Document processing failed: {document['error_message']}")
        if time.monotonic() >= deadline:
            print(f"FAIL: processing timeout, document stayed {document['status']}", file=sys.stderr)
            raise SystemExit(2)
        time.sleep(1)
        document = request(f"/api/documents/{document['id']}")
    assert EXPECTED_TEXT in document["extracted_text"], document["extracted_text"]
    assert document["word_count"] > 0
    assert document["char_count"] >= len(EXPECTED_TEXT)
    assert document["error_message"] is None
    print(f"PASS: PDF processed, text verified ({len(pdf)} bytes)", flush=True)


if __name__ == "__main__":
    main()
