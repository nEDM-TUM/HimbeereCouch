#!/usr/bin/env python
import signal
import threading as _th
import multiprocessing as _mp
import time
import os
from .util import Daemon, getmacid, getpassword
from .log import MPLogHandler, flush_log_to_db, log
from .database import set_server, get_database, get_processes_code
from .rpc import RaspServerProcess, start_new_process
from .misc import execute_cmd, receive_broadcast_message


class ShouldExit(Exception):
    pass

class ReloadDaemon(Exception):
    pass

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
            for l in ch:
                if l is None and daemon.should_quit(): raise ShouldExit()
                if l is None:
                    # Take care of housekeeping on the heartbeats
                    flush_log_to_db(adb)
                    send_heartbeat(db=adb,running_ids=ids.running_ids)
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
            daemon.reload()
            return
        except ShouldExit:
            return
        except Exception as e:
            log("Exception seen: " + repr(e))
            if daemon.should_quit(): return
            time.sleep(5)

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
        for anid, code in code_list.items():
            processes[anid] = start_new_process(anid, code)
        ids.ids = code_list.keys()

        serv.accept_connection(len(processes))

        exit_req = False
        while len(processes) > 0:
            del_list = []
            for anid,x in processes.items():
                t,q = x
                try:
                    res = q.get(False,0.2)
                    t.join()
                    if "ok" not in res:
                        log("Error seen ({}) : {}".format(k, res["error"]))
                    del_list.append(anid)
                except _mp.Queue.Empty:
                    pass
                if self.should_quit() and not exit_req:
                    serv.exit()
                    exit_req = True
            for t in del_list: del processes[t]
            ids.running_ids = processes.keys()

    def run(self):

        def _handler(sn, *args):
            if sn == signal.SIGHUP:
                log("Reload requested")
                self._is_reloading = True
            elif not self._should_quit:
                log("Quit requested")
            self._should_quit = True

        def _listen_for_new_server(o, to):
            asrv = receive_broadcast_message(to)
            if not asrv:
                return False
            open(o.server_file, "w").write(asrv)
            self.reload()
            return True

        if not os.path.exists(self.server_file):
            if not _listen_for_new_server(self, 120):
                return
        else:
            t = _th.Thread(target=_listen_for_new_server, args=(self, 0))
            t.daemon = True
            t.start()

        server = open(self.server_file).read()
        set_server(server)

        for s in [signal.SIGINT, signal.SIGTERM, signal.SIGHUP]:
            signal.signal(s, _handler)

        while True:
            self._is_reloading, self._should_quit  = False, False
            ids = IDCache()
            t = _th.Thread(target=listen_daemon, args=(ids,self))
            t.start()

            log("Starting, with server: %s" % server)
            try:
                self.run_as_daemon(lock_obj)
            except Exception as e:
                log("Received exception: " + repr(e))

            while not self.should_quit():
                time.sleep(1.0)

            t.join()

            if self._is_reloading:
                log("Reloading...")
                continue

            if self.should_quit(): break

def run_daemon(cmd, sf, apath):
    join = os.path.join
    daemon = RaspberryDaemon(join(apath, 'rspby_daemon.pid'),
                             stdout=join(apath, 'rspby_daemon.log'),
                             stderr=join(apath, 'rspby_daemon.err'),
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


