"""Inbound email ingest: parse forwarded mail, write it to the learner's inbox/ as untrusted data and
enqueue an intake job. A library: the gateway supplies the UserDirectory, WorkspaceWriter and JobQueue.
See CONTRACTS.md section 7.
"""

from mentor_email_ingest.handler import UNTRUSTED_BANNER, InboundHandler, sanitize_filename, slugify
from mentor_email_ingest.parser import ParsedEmail, decode_bytes, html_to_text, parse_message

__all__ = [
    "UNTRUSTED_BANNER",
    "InboundHandler",
    "ParsedEmail",
    "decode_bytes",
    "html_to_text",
    "parse_message",
    "sanitize_filename",
    "slugify",
]
