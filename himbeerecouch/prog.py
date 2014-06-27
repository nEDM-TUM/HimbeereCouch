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
from .util import Daemon, getmacid, getpassword, blink_leds, stop_blinking

_should_quit = False
_listen_should_quit = False
_broadcast_port = 53000

_export_cmds = ["should_quit", "log", "get_acct"]

def should_quit(): 
    return _should_quit

def get_acct():
    acct = cloudant.Account(_server)
    assert acct.login(getmacid(), getpassword()).status_code == 200
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
        global _should_quit
        def handler(*args):
            global _should_quit, _listen_should_quit
            if not _should_quit: log("Quit requested")
            _listen_should_quit = True
            _should_quit = True

        signal.signal(signal.SIGTERM, handler)
        signal.signal(signal.SIGINT, handler)

        lock_obj = { "lock" : _th.Lock(), "ids" : [] }
        t = _th.Thread(target=listen_daemon, args=(lock_obj,))
        t.start()
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
        t.join()

def run_daemon(cmd, server, apath):
    daemon = RaspberryDaemon(apath + 'daemon-example.pid', 
                             stdout=apath + 'daemon-example.log', 
                             stderr=apath + 'daemon-example.err')
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
    
    msg, addr = s.recvfrom(1024)
    dic = json.loads(msg)
    s.sendto(json.dumps(dict(MacID=getmacid(),password=getpassword())), addr)
    stop_blinking(v)
    return dic['server']
