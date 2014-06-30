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
_listen_should_quit = False
_broadcast_port = 53000
_server = None

_export_cmds = ["should_quit", "log", "get_acct"]

def should_quit(): 
    return _should_quit

def get_acct():
    acct = cloudant.Account(_server)
    if acct.login(getmacid(), getpassword()).status_code == 200:
        raise Exception("Server (%s) credentials invalid!" % _server)
    return acct

def log(args):
    sys.stdout.write(str(datetime.datetime.now()) + ' [RSPBRY] ' + str(args)+'\n')
    sys.stdout.flush()


def listen_daemon(lock_obj):
    try:
        global _should_quit
        acct = get_acct()
        adb = acct["nedm_head"]
        ch = adb.changes(params=dict(feed='continuous',
                                     heartbeat=5000,
                                     since='now',
                                     filter='nedm_default/doc_type',
                                     type=getmacid(),
                                     handle_deleted=True),
                                     emit_heartbeats=True)
        for l in ch:
            if l is None and _listen_should_quit: break
            if l is None: continue
            # Force reload
            should_stop = False
            if "deleted" in l:
                lock_obj['lock'].acquire()
                if l['id'] in lock_obj['ids']: should_stop = True
                lock_obj['lock'].release()
            else:
                should_stop = True
            if should_stop: 
                log("Forcing a restart, because new document arrived/got deleted")
                _should_quit = True
    except Exception as e:
        log("Exception seen: " + repr(e))
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
        db = acct["nedm_head"]
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
                if not t.isAlive(): del_list.append(t)
            for t in del_list: threads.remove(t) 

    def run(self):
        global _should_quit, _server
        def handler(*args):
            global _should_quit, _listen_should_quit
            if not _should_quit: log("Quit requested")
            _listen_should_quit = True
            _should_quit = True

        def _listen_for_new_server(o, restart_if_True=False):
            asrv = receive_broadcast_message(120)
            if not asrv:
                return False
            open(o.server_file, "w").write(asrv["server"])
            if restart_if_True:
                o.restart()
            return True


        threads = []
        if not os.path.exists(self.server_file):
            if not _listen_for_new_server(self.server_file):
                return
        else:
            t = _th.Thread(target=_listen_for_new_server, args=(self, True))
            t.start()
            threads.append(t)


        _server = open(self.server_file).read()


        signal.signal(signal.SIGTERM, handler)
        signal.signal(signal.SIGINT, handler)

        lock_obj = { "lock" : _th.Lock(), "ids" : [] }
        t = _th.Thread(target=listen_daemon, args=(lock_obj,))
        t.start()
        threads.append(t)
        while 1:
            try:
                log("Starting...")
                self.run_as_daemon(lock_obj)
                if _listen_should_quit: break
            except Exception as e:
                log("Received exception: " + repr(e))
            finally:
                _should_quit = False
                log("Pausing before restart....")
                time.sleep(5)
        for t in threads: t.join()

def run_daemon(cmd, sf, apath):
    daemon = RaspberryDaemon(apath + 'rspby_daemon.pid', 
                             stdout=apath + 'rspby_daemon.log', 
                             stderr=apath + 'rspby_daemon.err',
                             server_file=sf)
    if 'start' == cmd:
        daemon.start()
    elif 'stop' == cmd:
        daemon.stop()
    elif 'restart' == cmd:
        daemon.restart()
    else:
        print "usage: start|stop|restart" 

def broadcast_message(server_name):
    """
      Broadcasts the desired couchdb server name to listening Raspberry Pis 
      
      Waits and returns responses from any connected RPs.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('', 0))
    s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    
    send_data = json.dumps(dict(server=server_name))
    print "Broadcasting... :" + send_data
    s.sendto(send_data, ('<broadcast>', _broadcast_port))

    s.settimeout(10)
    list_of_devices = [] 
    while 1:
        try:
            msg, addr = s.recvfrom(1024) 
        except socket.timeout: 
            break
        list_of_devices.append((json.loads(msg), addr))
    return list_of_devices
     

def receive_broadcast_message(timeout=1000):
    """
      Receives broadcast message and returns MAC id and password
    """
    v = blink_leds() 
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(('<broadcast>', _broadcast_port))
    s.settimeout(timeout)

    def _handler(*args):
       pass

    oh = signal.signal(signal.SIGTERM, _handler)
    
    try:
        msg, addr = s.recvfrom(1024)
        dic = json.loads(msg)
        s.sendto(json.dumps(dict(MacID=getmacid(),password=getpassword())), addr)
        return dic['server']
    except:
        return None
    finally:
        stop_blinking(v)
        signal.signal(signal.SIGTERM, oh)
