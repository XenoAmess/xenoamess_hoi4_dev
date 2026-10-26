import time

from tools.common import write_json as common_write_json


def write_json(path, value):
    delays = (0.02, 0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16, None)
    for delay in delays:
        try:
            common_write_json(path, value)
            return
        except OSError as exc:
            if getattr(exc, "winerror", None) != 1175 or delay is None:
                raise
            time.sleep(delay)
