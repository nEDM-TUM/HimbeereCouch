#!/usr/bin/env python
import imp
import cloudant
import signal
import threading as _th
import time
import sys
import datetime
import json
import socket
import os
from .util import Daemon, getmacid, getpassword, blink_leds, stop_blinking

_should_quit = False
_broadcast_port = 53000
_max_broadcast_packet = 65000
_is_reloading = False
_server = None
_database_name = "nedm%2Fraspberries"

_export_cmds = [
  "should_quit",
  "get_acct",
  "register_quit_notification",
  "remove_quit_notification"
]
_current_log = []
_current_log_lock = _th.Lock()
_should_quit_notifiers = set()

def register_quit_notification(afunc):
    if not afunc: return
    _should_quit_notifiers.add(afunc)

def remove_quit_notification(afunc):
    if not afunc: return
    try:
        _should_quit_notifiers.remove(afunc)
    except KeyError: pass

def should_quit():
    return _should_quit

def get_acct():
    acct = cloudant.Account(_server)
    if acct.login(str(getmacid()), str(getpassword())).status_code != 200:
        raise Exception("Server (%s) credentials invalid!" % _server)
    return acct

def log(*args, **kwargs):
    global _current_log
    a = list(args)
    if kwargs.get("thread_label"):
        a.insert(0, kwargs["thread_label"])
    alog = [str(datetime.datetime.utcnow()), " ".join(map(str,a))]
    sys.stdout.write(' [RSPBRY] '.join(alog)+'\n')
    sys.stdout.flush()

    # Put in the queue to be written
    _current_log_lock.acquire()
    _current_log.append(alog)
    _current_log_lock.release()

def _gen_log(alabel):
    def _f(*args):
        return log(*args, thread_label=alabel)
    return _f

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

def send_heartbeat(db):
    """
      Update the update document
    """
    db.design("nedm_default").put("_update/insert_with_timestamp/%s_heartbeat" % str(getmacid()),
      params=dict(type="heartbeat"))


def execute_cmd(dic):
    import subprocess as _sp
    try:
        p = _sp.Popen(dic["cmd"], stderr=_sp.PIPE, stdout=_sp.PIPE)
        dic["ret"] = list(p.communicate())
    except Exception as e:
        dic["ret"] = [None,repr(e)]

def listen_daemon(lock_obj):
    try:
        acct = get_acct()
        adb = acct[_database_name]
        mi = str(getmacid())
        ch = adb.changes(params=dict(feed='continuous',
                                     heartbeat=5000,
                                     include_docs=True,
                                     since='now',
                                     filter='nedm_default/doc_type',
                                     type=[mi, mi+"_cmd"],
                                     handle_deleted=True),
                                     emit_heartbeats=True)
        for l in ch:
            if l is None and should_quit(): break
            if l is None:
                # Take care of housekeeping on the heartbeats
                flush_log_to_db(adb)
                send_heartbeat(adb)
                continue
            # Force reload
            should_stop = False
            if "deleted" in l:
                lock_obj['lock'].acquire()
                if l['id'] in lock_obj['ids']: should_stop = True
                lock_obj['lock'].release()
            else:
                # See if it's a cmd doc
                t = l["doc"]
                if t['type'] == mi + '_cmd':
                     if "ret" in t: continue
                     execute_cmd(t)
                     adb.post("_bulk_docs", params=dict(docs=[t]))
                else:
                     should_stop = True
            if should_stop:
                log("Forcing a restart, because new document arrived/got deleted")
                lock_obj["obj"].reload()
                break
    except Exception as e:
        log("Exception seen: " + repr(e))
        if should_quit(): return
        time.sleep(5)
        listen_daemon(lock_obj)

class RaspberryDaemon(Daemon):
    def __init__(self, pid_file, server_file="", **kwargs):
        Daemon.__init__(self, pid_file, **kwargs)
        self.server_file = server_file

    def run_as_daemon(self, lo):

        def add_code(adoc):
            """
              add_code is a helper function to build a module from code
            """
            anid = adoc['_id']
            adoc['mod'] = imp.new_module(anid)
            am = adoc['mod']
            exec adoc['code'] in am.__dict__
            for cmd in _export_cmds:
                am.__dict__[cmd] = globals()[cmd]
            am.__dict__["log"] = _gen_log("[%s]" % anid)
            return anid, adoc

        def start_thread(adaemon):
            """
              start an independent thread
            """
            def _daemon_func(amod, retval):
                try:
                    amod.main()
                except Exception as e:
                    retval['error'] = repr(e)
                if not 'error' in retval:
                    retval['ok'] = True

            q = {}
            t=_th.Thread(target=_daemon_func, args=(adaemon['mod'], q))
            t.start()
            t.result = q
            return t


        acct = get_acct()
        db = acct[_database_name]
        aview = db.design("document_type").view("document_type")
        res = aview.get(params=dict(startkey=[getmacid()],
                                    endkey=[getmacid(), {}],
                                    include_docs=True,
                                    reduce=False)).json()

        daemons = dict([add_code(r['doc']) for r in res['rows']])
        threads = [start_thread(v) for _,v in daemons.items()]

        lo['lock'].acquire()
        lo['ids'] = [d['_id'] for d in daemons.values()]
        lo['lock'].release()

        while len(threads) > 0:
            del_list = []
            for t in threads:
                t.join(0.2)
                if not t.isAlive():
                    if "ok" not in t.result:
                        log("Error seen: " + str(t.result))
                    del_list.append(t)
            for t in del_list: threads.remove(t)

    def run(self):
        global _should_quit, _server, _is_reloading

        def _handler(sn, *args):
            global _should_quit, _is_reloading
            if sn == signal.SIGHUP:
                log("Reload requested")
                _is_reloading = True
            elif not _should_quit:
                log("Quit requested")
            _should_quit = True
            for f in _should_quit_notifiers: f()

        def _listen_for_new_server(o, to):
            asrv = receive_broadcast_message(to)
            if not asrv:
                return False
            open(o.server_file, "w").write(asrv)
            self.reload()
            return True


        _is_reloading, _should_quit  = False, False

        threads = []
        if not os.path.exists(self.server_file):
            if not _listen_for_new_server(self, 120):
                return
        else:
            t = _th.Thread(target=_listen_for_new_server, args=(self, 0))
            t.start()
            threads.append(t)


        _server = open(self.server_file).read()


        for s in [signal.SIGINT, signal.SIGINT, signal.SIGHUP]:
            signal.signal(s, _handler)

        lock_obj = { "lock" : _th.Lock(), "ids" : [], "obj" : self }
        t = _th.Thread(target=listen_daemon, args=(lock_obj,))
        t.start()
        threads.append(t)

        log("Starting, with server: %s" % _server)
        try:
            self.run_as_daemon(lock_obj)
        except Exception as e:
            log("Received exception: " + repr(e))

        while not should_quit():
            time.sleep(1.0)

        for t in threads: t.join()

        # If we need to reload, then recall this function
        if _is_reloading:
            log("Reloading...")
            return self.run()

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

def broadcast_message(server_name="", send_data=None, timeout=10):
    """
      Broadcasts the desired couchdb server name to listening Raspberry Pis

      Waits and returns responses from any connected RPs.
    """

    # Set up the socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('', 0))
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    # determine what we're sending
    if not send_data:
        send_data = json.dumps(dict(server=server_name))
    else:
        send_data = json.dumps(send_data)

    if len(send_data) > _max_broadcast_packet:
        raise Exception("Length of sent data (%i) exceeds max (%i)" % (len(send_data), _max_broadcast_packet))

    s.sendto(send_data, ('<broadcast>', _broadcast_port))

    s.settimeout(timeout)

    list_of_devices = {}
    while 1:
        try:
            msg, addr = s.recvfrom(_max_broadcast_packet)
            list_of_devices[addr] = msg
        except socket.timeout:
            break
    for k in list_of_devices:
        list_of_devices[k] = json.loads(list_of_devices[k])

    return list_of_devices


def receive_broadcast_message(timeout=1000):
    """
      Receives broadcast message and returns MAC id and password
    """
    v = blink_leds()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('<broadcast>', _broadcast_port))
    total_timeout = timeout
    s.settimeout(1.0)

    oh = None
    try:
        # Handle SIGTERM if we are on the main thread
        def _handler(*args):
           pass
        oh = signal.signal(signal.SIGTERM, _handler)
    except: pass

    log("Wait for broadcast...")
    while 1:
        try:
            msg, addr = s.recvfrom(_max_broadcast_packet)
            dic = json.loads(msg)
            if "server" in dic:
                s.sendto(json.dumps(dict(MacID=getmacid(),password=getpassword())), addr)
                log("Received...")
                return dic['server']
            elif all(k in dic for k in ("MacID", "password", "cmd")):
                if dic["MacID"] == getmacid() and \
                   dic["password"] == getpassword():
                    # Means this is for me
                    log("Running cmd: " + str(dic["cmd"]))
                    execute_cmd(dic)
                    astr = json.dumps(dic)
                    if len(astr) > _max_broadcast_packet:
                        raise Exception("Length of sent data (%i) exceeds max (%i)" % (len(astr), _max_broadcast_packet))
                    s.sendto(json.dumps(dic), addr)
        except Exception as e:
            if e.__class__ == socket.timeout:
                if should_quit(): return None
                if timeout <= 0: continue
                total_timeout -= 1.0
                if total_timeout > 0: continue
                log("Timed out...")
            else:
                log("Exception: " + repr(e))
            return None
        finally:
            stop_blinking(v)
            if oh: signal.signal(signal.SIGTERM, oh)
