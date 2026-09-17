"""Regression tests for bounded and fragmented upstream WebSocket frames."""
import asyncio
import struct

import pytest

from app.tg_proxy_engine.raw_websocket import RawWebSocket


class _Writer:
    def __init__(self):
        self.data = bytearray()

    def write(self, data):
        self.data.extend(data)

    async def drain(self):
        return None


async def _recv_from(data: bytes):
    reader = asyncio.StreamReader()
    reader.feed_data(data)
    reader.feed_eof()
    return await RawWebSocket(reader, _Writer()).recv()


def test_fragmented_binary_message_is_reassembled():
    # Server frames are unmasked: binary FIN=0 followed by continuation FIN=1.
    frames = bytes([0x02, 3]) + b"abc" + bytes([0x80, 3]) + b"def"
    assert asyncio.run(_recv_from(frames)) == b"abcdef"


def test_oversized_frame_is_rejected_before_payload_read():
    async def run_case():
        length = RawWebSocket.MAX_MESSAGE_LEN + 1
        header = bytes([0x82, 127]) + struct.pack(">Q", length)
        reader = asyncio.StreamReader()
        reader.feed_data(header)
        reader.feed_eof()
        ws = RawWebSocket(reader, _Writer())
        with pytest.raises(ConnectionError, match="frame too large"):
            await ws.recv()

    asyncio.run(run_case())
