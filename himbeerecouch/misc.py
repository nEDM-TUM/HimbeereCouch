import socket
import signal
import json
from .util import getmacid, getpassword, blink_leds, stop_blinking
from .log import log

_broadcast_port = 53000
_max_broadcast_packet = 65000

def execute_cmd(dic):
    import subprocess as _sp
    try:
        p = _sp.Popen(dic["cmd"], stderr=_sp.PIPE, stdout=_sp.PIPE)
        dic["ret"] = list(p.communicate())
    except Exception as e:
        dic["ret"] = [None,repr(e)]


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
        except Exception as e:
            if e.__class__ == socket.timeout:
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
