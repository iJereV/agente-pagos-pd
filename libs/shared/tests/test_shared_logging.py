import logging

from shared.logging import setup_logging


def test_access_logs_are_silenced() -> None:
    setup_logging()
    access = logging.getLogger("uvicorn.access")
    # uvicorn only writes access lines when this logger has handlers somewhere.
    assert not access.hasHandlers()
    assert logging.getLogger("uvicorn.error").hasHandlers()
