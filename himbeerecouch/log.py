import sys
import logging
import traceback
import threading
import multiprocessing
from logging import StreamHandler as SH

_current_log = []
_current_log_lock = threading.Lock()

def flush_log_to_db(db):
    """
      Flush the log to the database
    """
    global _current_log
    # Grab the current log
    _current_log_lock.acquire()
    thelog = _current_log
    _current_log = []
    _current_log_lock.release()

    if len(thelog) == 0: return
    db.design("raspberry_def").put(
        "_update/update_log/%s_log?remove_since=50000" % str(getmacid()),
        params=dict(log=thelog))


# ============================================================================
# Define Log Handler
# ============================================================================
class MPLogHandler(logging.Handler):
    """multiprocessing log handler

    This handler makes it possible for several processes
    to log to the same file by using a queue.

    """
    def __init__(self):
        logging.Handler.__init__(self)

        self._handler = SH()
        self.queue = multiprocessing.Queue(-1)

        thrd = threading.Thread(target=self.receive)
        thrd.daemon = True
        thrd.start()

    def setFormatter(self, fmt):
        logging.Handler.setFormatter(self, fmt)
        self._handler.setFormatter(fmt)

    def receive(self):
        while True:
            try:
                record = self.queue.get()
                self._handler.emit(record)

                _current_log_lock.acquire()
                _current_log.append(record)
                _current_log_lock.release()
            except (KeyboardInterrupt, SystemExit):
                raise
            except (EOFError,TypeError):
                break
            except:
                traceback.print_exc(file=sys.stderr)

    def send(self, s):
        self.queue.put_nowait(s)

    def _format_record(self, record):
        if record.args:
            record.msg = record.msg % record.args
            record.args = None
        if record.exc_info:
            dummy = self.format(record)
            record.exc_info = None

        return record

    def emit(self, record):
        try:
            s = self._format_record(record)
            self.send(s)
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)

    def close(self):
        self._handler.close()
        logging.Handler.close(self)


_logger = logging.getLogger("RSPBY")
_logger.setLevel(logging.INFO)
_formatter = logging.Formatter("%(asctime)s [%(name)s/%(processName)s] %(levelname)s %(message)s")
_handler = MPLogHandler()
_handler.setFormatter(_formatter)
_logger.addHandler(_handler)
log = _logger.info

