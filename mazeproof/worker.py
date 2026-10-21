"""One disposable decoder process; parent enforces wall time and RSS budgets."""

import multiprocessing
import queue
import threading
import time

from .core import Rejected

MAX_MEMORY = 512 * 1024 * 1024
MAX_SECONDS = 30


def _entry(connection, operation, arguments):
    try:
        if operation == "inspect":
            from .imaging import inspect

            result = inspect(**arguments)
        elif operation == "structure":
            from .core import validate_structure

            result = validate_structure(**arguments)
        else:
            raise Rejected("INVALID_INPUT", "WORKER_OPERATION")
        connection.send((True, result))
    except Rejected as error:
        connection.send((False, (error.status, error.code)))
    except (MemoryError, OverflowError):
        connection.send((False, ("RESOURCE_LIMIT", "MEMORY_LIMIT")))
    except Exception:
        connection.send((False, ("ERROR", "WORKER_FAILED")))
    finally:
        connection.close()


def run(operation, arguments, *, seconds=MAX_SECONDS, memory=MAX_MEMORY):
    import psutil

    context = multiprocessing.get_context("spawn")
    parent, child = context.Pipe(duplex=False)
    process = context.Process(
        target=_entry, args=(child, operation, arguments), daemon=True
    )
    process.start()
    child.close()
    deadline = time.monotonic() + seconds
    received = queue.Queue(maxsize=1)

    def receive():
        try:
            received.put(parent.recv())
        except (EOFError, OSError):
            received.put((False, ("ERROR", "WORKER_EXIT")))

    # recv() may block after the first pipe chunk. Keep the resource watchdog
    # running while receiving/deserializing a large normalized preview.
    receiver = threading.Thread(target=receive, daemon=True)
    receiver.start()
    try:
        while True:
            if time.monotonic() > deadline:
                raise Rejected("RESOURCE_LIMIT", "WORKER_TIMEOUT")
            try:
                if psutil.Process(process.pid).memory_info().rss > memory:
                    raise Rejected("RESOURCE_LIMIT", "MEMORY_LIMIT")
            except psutil.NoSuchProcess:
                pass
            try:
                ok, result = received.get(timeout=0.02)
            except queue.Empty:
                continue
            if not ok:
                raise Rejected(*result)
            return result
    finally:
        if process.is_alive():
            process.terminate()
        process.join(timeout=1)
        if process.is_alive():
            process.kill()
            process.join(timeout=1)
        parent.close()
        receiver.join(timeout=1)
        process.close()
