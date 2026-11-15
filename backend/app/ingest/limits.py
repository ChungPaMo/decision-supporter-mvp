"""Request-byte cap for assistance endpoints, including chunked multipart requests."""
import io
from app.errors import ApiError, ErrorCode
from app.exports.limits import _respond

MAX_REQUEST_BYTES = 51 * 1024 * 1024  # 50 MiB files + bounded multipart/settings overhead.
PATHS = {'/ingest/profile', '/ingest/mapping-suggestions', '/ingest/transform-preview'}


class AssistanceBodyLimit:
    def __init__(self, app, limit=MAX_REQUEST_BYTES):
        self.app, self.limit = app, limit

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope['path'].rstrip('/') not in PATHS:
            await self.app(scope, receive, send)
            return
        error = ApiError(413, ErrorCode.FILE_TOO_LARGE, 'Ingestion assistance request exceeds byte limit.')
        declared = dict(scope.get('headers', [])).get(b'content-length', b'')
        if declared.isdigit() and int(declared) > self.limit:
            await _respond(send, error)
            return
        # BytesIO bounds overhead even if a client sends millions of tiny chunks.
        body = io.BytesIO()
        while True:
            message = await receive()
            if message['type'] != 'http.request':
                body.close()
                return
            chunk = message.get('body', b'')
            if body.tell() + len(chunk) > self.limit:
                body.close()
                await _respond(send, error)
                return
            body.write(chunk)
            if not message.get('more_body', False):
                break
        body.seek(0)
        async def replay():
            chunk = body.read(64 * 1024)
            return {'type': 'http.request', 'body': chunk, 'more_body': body.tell() < body.getbuffer().nbytes}
        try:
            await self.app(scope, replay, send)
        finally:
            body.close()
