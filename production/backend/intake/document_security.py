"""Bounded in-memory upload and fail-closed local malware scanning."""
import socket
import struct

from django.conf import settings
from django.core.files.uploadhandler import MemoryFileUploadHandler, StopUpload

MAX_PDF = 5 * 1024 * 1024
MAX_REQUEST = MAX_PDF + 64 * 1024


class BoundedMemoryUploadHandler(MemoryFileUploadHandler):
    """Never spill a plaintext original to Django temporary upload files."""
    def handle_raw_input(self, input_data, META, content_length, boundary, encoding=None):
        if content_length is None or not 0 < content_length <= MAX_REQUEST:
            raise StopUpload(connection_reset=True)
        self.activated = True
        self.seen = 0
        self.files = 0

    def new_file(self, *args, **kwargs):
        self.files += 1
        if self.files != 1:
            self.request._compass_upload_rejected = True
            raise StopUpload(connection_reset=True)
        super().new_file(*args, **kwargs)

    def receive_data_chunk(self, raw_data, start):
        self.seen += len(raw_data)
        if self.seen > MAX_PDF:
            self.request._compass_upload_rejected = True
            raise StopUpload(connection_reset=True)
        return super().receive_data_chunk(raw_data, start)


def looks_like_pdf(data):
    # Signature/EOF checks are only a format filter, not a safety guarantee.
    return (0 < len(data) <= MAX_PDF and data.startswith(b"%PDF-")
            and data.rstrip().endswith(b"%%EOF"))


def scan_pdf(data):
    """ClamAV INSTREAM on an explicitly mounted local Unix socket.

    No shell, no third-party upload, no external network. Exact clean reply
    required; unknown replies, timeout, malware, scanner failure all deny.
    """
    path = getattr(settings, "DOCUMENT_SCANNER_SOCKET", "")
    if not path or not hasattr(socket,"AF_UNIX") or not looks_like_pdf(data):
        return False
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
            client.settimeout(5)
            client.connect(path)
            client.sendall(b"zINSTREAM\x00")
            for start in range(0,len(data),65536):
                chunk=data[start:start+65536]
                client.sendall(struct.pack("!I",len(chunk))+chunk)
            client.sendall(b"\x00"*4)
            reply=bytearray()
            while b"\x00" not in reply and len(reply)<1024:
                part=client.recv(1024)
                if not part:
                    break
                reply.extend(part)
            return bytes(reply)==b"stream: OK\x00"
    except (OSError, ValueError):
        return False
