import sys
import logging
import traceback
import threading
import multiprocessing
from multiprocessing.util import register_after_fork
import atexit
import Queue
from .util import getmacid
from logging import FileHandler as FH
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
    def __init__(self, out_file = None):
        logging.Handler.__init__(self)

        if out_file is not None:
            self._handler = FH(out_file)
        else:
            self._handler = SH()
        self.queue = multiprocessing.Queue(-1)

        atexit.register(logging.shutdown)
        self._thrd = None
        self.start_recv_thread()
        self._is_child = False

        # Children will automatically register themselves as chilcren
        register_after_fork(self, MPLogHandler.set_is_child)

    def set_is_child(self):
        self._is_child = True

    def start_recv_thread(self):
        if self._thrd: return
        self._shutdown = False
        thrd = threading.Thread(target=self.receive)
        thrd.daemon = True
        thrd.start()
        self._thrd = thrd

    def setFormatter(self, fmt):
        logging.Handler.setFormatter(self, fmt)
        self._handler.setFormatter(fmt)

    def receive(self):
        while not self._shutdown:
            try:
                record = self.queue.get(True, 0.3)
                self._handler.emit(record)

                _current_log_lock.acquire()
                _current_log.append(self.format(record))
                _current_log_lock.release()
            except (Queue.Empty,IOError):
                pass
            except (KeyboardInterrupt, SystemExit):
                raise
            except (EOFError,TypeError):
                break
            except:
                traceback.print_exc(file=sys.stderr)

    def shutdown_recv_thread(self):
        if self._thrd:
            self._shutdown = True
            self._thrd.join()
            self._thrd = None

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
            # If we are a child, then send the record, otherwise simply emit it
            if self._is_child: self.send(s)
            else: self._handler.emit(s)
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)

    def close(self):
        self._handler.close()
        self.shutdown_recv_thread()
        logging.Handler.close(self)


_logger = logging.getLogger()
_logger.setLevel(logging.INFO)
_formatter = logging.Formatter("%(asctime)s [RSPBY/%(processName)s] %(levelname)s %(message)s")
_handler = None
log = _logger.info

# Suppress unnecessary output from requests
requests_log = logging.getLogger("requests.packages.urllib3")
requests_log.setLevel(logging.WARN)

def set_logging_file(out_file=None):
    global _handler
    if _handler is not None:
        _logger.removeHandler(_handler)
    _handler = MPLogHandler(out_file)
    _handler.setFormatter(_formatter)
    _logger.addHandler(_handler)

set_logging_file()

def continue_logging():
    if _handler:
        _handler.start_recv_thread()

def pause_logging():
    if _handler:
        _handler.shutdown_recv_thread()
