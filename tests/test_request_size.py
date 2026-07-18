import asyncio

from app.core.config import settings
from app.middleware.request_size import RequestSizeLimitMiddleware


def test_content_length_over_limit_is_rejected_before_endpoint(anonymous_client):
    response = anonymous_client.post(
        "/api/auth/login",
        content=b"{}",
        headers={
            "Content-Length": str(settings.max_request_size_bytes + 1),
            "Content-Type": "application/json",
        },
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "Request body is too large"}


def test_chunked_body_over_limit_is_rejected():
    async def consume_body(scope, receive, send):
        while True:
            message = await receive()
            if not message.get("more_body", False):
                break
        await send({"type": "http.response.start", "status": 204, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    messages = iter(
        [
            {"type": "http.request", "body": b"123", "more_body": True},
            {"type": "http.request", "body": b"456", "more_body": False},
        ]
    )
    sent_messages = []

    async def receive():
        return next(messages)

    async def send(message):
        sent_messages.append(message)

    middleware = RequestSizeLimitMiddleware(consume_body, max_bytes=5)
    scope = {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": "/upload",
        "raw_path": b"/upload",
        "query_string": b"",
        "headers": [(b"transfer-encoding", b"chunked")],
        "client": ("127.0.0.1", 1234),
        "server": ("testserver", 80),
    }

    asyncio.run(middleware(scope, receive, send))

    assert sent_messages[0]["status"] == 413
    assert b"Request body is too large" in sent_messages[1]["body"]
