from multiprocessing.connection import Listener, Client
import multiprocessing as _mp
from threading import Thread
from .log import log
from .database import get_acct
from .util import stack_trace
import traceback
import string
import random
import logging
import os
import signal
import json

def id_generator(size=6, chars=string.ascii_uppercase + string.digits):
   """
   Generates random ID, used for private shared key between processes
   """
   return ''.join(random.choice(chars) for _ in range(size))

_server = ('', 17000)
_authkey = id_generator(64)

class RPCObject(object):
    def __init__(self):
        def _output_handler(sig, fn):
            self.output_handler(sig, fn)
        signal.signal(signal.SIGUSR1, _output_handler)

    def output_handler(self, sn, fr):
        logging.info(
"""Dumping current stack information:

   {}

Complete""".format('\n   '.join(stack_trace(self.output_handler))))


class RPCServer(RPCObject):
    """
    RPC (Remote-Procedure-Call server)

    Calls remote procedures on all child processes
    """
    def __init__(self, address, authkey):
        super(RPCServer, self).__init__()
        self._clients = {}
        self._server_c = Listener(address, authkey=authkey)

    def output_handler(self, sn, fr):
        super(RPCServer, self).output_handler(sn, fr)
        for c in self._clients:
            try:
                os.kill(self._clients[c]["pid"], signal.SIGUSR1)
            except: pass

    def accept_connection(self, connections):
        for x in range(connections):
           client_c = self._server_c.accept()
           client_name = json.loads(client_c.recv())
           self._clients[client_c] = client_name

    def __getattr__(self, name):
        def do_rpc(*args, **kwargs):
            results = {}
            for c in self._clients:
                client_name = self._clients[c]["name"]
                try:
                    c.send((name, args, kwargs))
                    results[client_name] = c.recv()
                except:
                    results[client_name] = traceback.format_exc()
            for _, v in results.items():
                if isinstance(v, Exception):
                    raise v
            return results
        return do_rpc


class RPCProxy(RPCObject):
    """
    RPCProxy, object running in child processes that connects to an :class:`RPCServer`
    object.
    """
    def __init__(self, address, authkey):
        super(RPCProxy, self).__init__()
        self._functions = { }
        self._quitnotifiers = set()
        self._conn = Client(address, authkey=authkey)
        self._conn.send(json.dumps({"name" : _mp.current_process().name, "pid" : os.getpid()}))
        self._should_exit = False
        self.register_function(self.exit_now, "exit")
        def _exit(*args):
            self.exit_now()
        signal.signal(signal.SIGINT, _exit)
        signal.signal(signal.SIGTERM, _exit)

    def listen(self):
        def handle_client(client_c):
            while not self._should_exit:
                try:
                    func_name, args, kwargs = client_c.recv()
                except EOFError:
                    self.exit_now()
                    break
                try:
                    r = self._functions[func_name](*args,**kwargs)
                    client_c.send(r)
                except Exception as e:
                    client_c.send(e)
        self.t = Thread(target=handle_client, args=(self._conn,))
        self.t.daemon = True
        self.t.start()

    def register_exit_notification(self, func):
        self._quitnotifiers.add(func)

    def remove_exit_notification(self, func):
        try:
            self._quitnotifiers.remove(func)
        except KeyError: pass

    def exit_now(self):
        log("Exit requested")
        self._should_exit = True
        for f in self._quitnotifiers:
            f()
        return True

    def should_exit(self):
        return self._should_exit

    def register_function(self, func, name = None):
        if name is None:
            name = func.__name__
        self._functions[name] = func

class RaspProxyProcess(RPCProxy):
    def __init__(self):
        RPCProxy.__init__(self, _server,authkey=_authkey)

class RaspServerProcess(RPCServer):
    def __init__(self):
        RPCServer.__init__(self, _server,authkey=_authkey)


class ProcessImporter(object):
    """
    Handles importing classes/modules from code in database.

    See :func:`start_new_process` for an example of how this is used.

    """
    def __init__(self, modules, exported_commands = None):
        self._modules = modules
        if exported_commands is None:
            self._exported_commands = {}
        else:
            self._exported_commands = exported_commands
        self._already_exported = []

    def find_module(self, fullname, path=None):
        if fullname in self._modules:
            return self
        return None

    def load_module(self, name):
        import sys
        if name in sys.modules and name not in self._already_exported:
            return sys.modules[name]
        import imp
        mod = imp.new_module(name)
        exec self._modules[name] in mod.__dict__
        for cmd in self._exported_commands:
            mod.__dict__[cmd] = self._exported_commands[cmd]
        sys.modules[name] = mod
        self._already_exported.append(name)
        return mod


def start_new_process(name, code):
    """
      Start new child process

      :param name: Name of child process
      :type name: str
      :param code: code to run, dictionary of modules (in string format)
      :type code: dict
      :returns: (multiprocessing.Process, multiprocessing.Queue)

      The Queue returned has the result returned from the child process::

          { "ok" : True }

      when everything ok, and::

          { "error" : ...traceback... }

      when not.
    """
    def _new_proc(q):
        import sys
        # Use broadcaster from pynedm
        import pynedm.log as plog
        plog.use_broadcaster()
        o = RaspProxyProcess()
        sys.meta_path.append(
          ProcessImporter(code,
            {
            "log" : log,
            "get_acct" : get_acct,
            "should_quit" : o.should_exit,
            "register_quit_notification" : o.register_exit_notification,
            "remove_quit_notification" :  o.remove_exit_notification
            }
          )
        )
        o.listen()
        try:
            import main
            main.main()
            q.put({"ok" : True})
        except:
            q.put({"error" : traceback.format_exc()})

    q = _mp.Queue()
    t = _mp.Process(name=name, target=_new_proc, args=(q,))
    t.daemon = True
    t.start()
    return t, q

