#!/usr/bin/env python
import signal
import threading as _th
import time
import os
from .daemon import Daemon, ForceRestart
from .util import getmacid, getpassword, getipaddr
from .log import (MPLogHandler,
                  log,
                  start_child_logging,
                  stop_child_logging)
from .database import set_server, get_database, get_processes_code, send_heartbeat
from .rpc import RaspServerProcess, start_new_process
from .misc import execute_cmd, receive_broadcast_message
import Queue
import logging


_handled_signals = [signal.SIGINT, signal.SIGTERM, signal.SIGHUP]

class ShouldExit(Exception):
    """
    Raised when exit is requested
    """

class ReloadDaemon(Exception):
    """
    Raised to reload daemon
    """

class IDCache(object):
    def __init__(self):
        self._lock = _th.Lock()
        self._ids = set()
        self._running_ids = set()

    @property
    def ids(self):
        self._lock.acquire()
        ids = self._ids
        self._lock.release()
        return ids

    @property
    def running_ids(self):
        self._lock.acquire()
        ids = self._running_ids
        self._lock.release()
        return ids

    @ids.setter
    def ids(self, ids):
        self._lock.acquire()
        self._ids = set(ids)
        self._running_ids = set(ids)
        self._lock.release()

    @running_ids.setter
    def running_ids(self, ids):
        self._lock.acquire()
        self._running_ids = set(ids)
        self._lock.release()

    def __contains__(self, anid):
        self._lock.acquire()
        isin = anid in self._ids
        self._lock.release()
        return isin


def listen_daemon(ids, daemon):
    """
    Listen for changes in code in the database.
    """
    while 1:
        try:
            adb = get_database()
            mi = str(getmacid())
            ch = adb.changes(params=dict(feed='continuous',
                                         heartbeat=2000,
                                         include_docs=True,
                                         since='now',
                                         filter='nedm_default/doc_type',
                                         type=[mi, mi+"_cmd"],
                                         handle_deleted=True),
                                         emit_heartbeats=True)
            ip_addr = getipaddr()
            for l in ch:
                if l is None and daemon.should_quit(): raise ShouldExit()
                if l is None:
                    # Take care of housekeeping on the heartbeats
                    send_heartbeat(db=adb,running_ids=list(ids.running_ids), ip=ip_addr)
                    continue
                # Force reload
                if "deleted" in l:
                    if l['id'] in ids: raise ReloadDaemon()
                else:
                    # See if it's a cmd doc
                    t = l["doc"]
                    if t['type'] == mi + '_cmd':
                         if "ret" in t: continue
                         execute_cmd(t)
                         adb.post("_bulk_docs", params=dict(docs=[t]))
                    else:
                         raise ReloadDaemon()
        except ReloadDaemon:
            log("Forcing a restart, because new document arrived/got deleted")
            daemon.reload(True)
            return
        except ShouldExit:
            return
        except:
            logging.exception("Error in changes feed thread")
            if daemon.should_quit(): return
            time.sleep(5)

class ListenDaemon(object):
    """
	Utility class that handles starting/stopping listening (e.g.
	:func:`listen_daemon` and starts and stops logging of child processes.

    Example calling::

        with ListenDaemon(ids, self):
            ... # Perform code here while listening
    """
    def __init__(self, ids, daemon):
        self.ids = ids
        self.daemon = daemon
        self.t = None
        # start logging of children
        start_child_logging()

    def __enter__(self):
        self.t = _th.Thread(target=listen_daemon, args=(self.ids,self.daemon))
        self.t.start()

    def __exit__(self, *args):
        self.t.join()
        # stop logging of children
        stop_child_logging()

class RaspberryDaemon(Daemon):
    def __init__(self, pid_file, server_file="", **kwargs):
        Daemon.__init__(self, pid_file, **kwargs)
        self.server_file = server_file
        self._should_quit = False
        self._is_reloading = False

    def should_quit(self):
        return self._should_quit

    def run_as_daemon(self, ids):

        serv = RaspServerProcess()

        code_list = get_processes_code()
        processes = {}

        # Ignore handlers when starting new processes
        sig_hdlrs = {}
        for s in _handled_signals:
            sig_hdlrs[s] = signal.getsignal(s)
            signal.signal(s, signal.SIG_IGN)

        for aname, o in code_list.items():
            processes[o["id"]] = start_new_process(aname, o["code"])


        # Reset handlers
        for s in sig_hdlrs:
            signal.signal(s, sig_hdlrs[s])

        ids.ids = processes.keys()

        serv.accept_connection(len(processes))

        exit_req = False
        exit_time = None

        with ListenDaemon(ids, self):
            while len(processes) > 0:
                del_list = []
                for anid,x in processes.items():
                    t,q = x
                    try:
                        res = q.get(True,0.2)
                        t.join()
                        if "ok" not in res:
                            log("Error seen ({}) : {}".format(anid, res["error"]))
                        del_list.append(anid)
                    except (Queue.Empty,IOError):
                        pass
                    if self.should_quit() and not exit_req:
                        serv.exit()
                        exit_req = True
                        exit_time = time.time()

                for t in del_list: del processes[t]
                ids.running_ids = processes.keys()
                if exit_req and time.time() - exit_time > 20:
                    log("Time out waiting for processes, force terminate")
                    for t in processes:
                        os.kill(processes[t][0].pid, signal.SIGKILL)
                    log("Restart will be forced if not quitting")
                    raise ForceRestart()

    def run(self):

        def _handler(sn, *args):
            if sn == signal.SIGHUP:
                log("Reload requested")
                self._is_reloading = True
            elif not self._should_quit:
                log("Quit requested")
            self._should_quit = True

        if not os.path.exists(self.server_file):
            raise IOError("Server file not found")

        server = open(self.server_file).read()
        set_server(server)

        for s in _handled_signals:
            signal.signal(s, _handler)

        while True:
            self._is_reloading, self._should_quit  = False, False
            ids = IDCache()

            log("Starting, with server: {}".format(server))
            try:
                self.run_as_daemon(ids)
            except ForceRestart:
                # Force a brutal restart, one of the scripts misbehaved
                if self._is_reloading: raise
            except:
                logging.exception("Error run daemon")

            while not self.should_quit():
                time.sleep(1.0)

            if self._is_reloading:
                log("Reloading...")
                continue

            if self.should_quit(): break


def run_daemon(cmd, sf, apath):
    """
    Run daemon in non-blocking mode.

    :param sf: name of server file (path)
    :type sf: str 
    :param apath: path to output logs/pid files 
    :type apath: str 
    """
    join = os.path.join
    daemon = RaspberryDaemon(join(apath, 'rspby_daemon.pid'),
                             stdout=join(apath, 'rspby_daemon.log'),
                             server_file=sf)
    if 'start' == cmd:
        daemon.start()
    elif 'stop' == cmd:
        daemon.stop()
    elif 'restart' == cmd:
        daemon.restart()
    elif 'reload' == cmd:
        daemon.reload()
    else:
        print "usage: start|stop|restart|reload"

def run(sf):
    """
    Run daemon in blocking mode (e.g. with supervisord)

    :param sf: name of server file (path)
    :type sf: str 
    """
    daemon = RaspberryDaemon("/dev/null",
                             server_file=sf)
    daemon.run()
