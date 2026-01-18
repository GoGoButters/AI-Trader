"""
FastAPI Routes for Real-Time Logs
"""

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from collections import deque
import asyncio
import json
import logging

router = APIRouter(prefix="/api/logs", tags=["logs"])

# In-memory log buffer (circular buffer for last 500 logs)
log_buffer = deque(maxlen=500)


class LogHandler(logging.Handler):
    """Custom handler to capture logs for API streaming"""

    def emit(self, record):
        try:
            log_entry = {
                "timestamp": self.formatter.formatTime(record)
                if self.formatter
                else record.created,
                "level": record.levelname,
                "module": record.module,
                "message": record.getMessage(),
            }
            log_buffer.append(log_entry)
        except Exception:
            pass


# Install global log handler
_handler_installed = False


def install_log_handler():
    global _handler_installed
    if not _handler_installed:
        handler = LogHandler()
        handler.setFormatter(logging.Formatter("%(asctime)s"))
        logging.getLogger("backend").addHandler(handler)
        _handler_installed = True


@router.get("/recent")
async def get_recent_logs(limit: int = 100):
    """Get recent logs from buffer"""
    install_log_handler()
    logs = list(log_buffer)[-limit:]
    return {"logs": logs, "total": len(log_buffer)}


@router.get("/stream")
async def stream_logs():
    """Server-Sent Events stream for real-time logs"""
    install_log_handler()

    async def event_generator():
        last_index = len(log_buffer)

        while True:
            current_len = len(log_buffer)

            # Send new logs if available
            if current_len > last_index:
                new_logs = list(log_buffer)[last_index:]
                for log in new_logs:
                    yield f"data: {json.dumps(log)}\n\n"
                last_index = current_len

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )
