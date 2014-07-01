#!/usr/bin/env python

"""
  From: http://www.jejik.com/articles/2007/02/a_simple_unix_linux_daemon_in_python/
  Author: Sander Marechal
"""

import sys, os, time, atexit
from signal import SIGTERM, SIGHUP 
import hashlib, uuid
import threading 

class Daemon:
    """
    A generic daemon class.
    
    Usage: subclass the Daemon class and override the run() method
    """
    def __init__(self, pidfile, stdin='/dev/null', stdout='/dev/null', stderr='/dev/null'):
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.pidfile = pidfile
    
    def daemonize(self):
        """
        do the UNIX double-fork magic, see Stevens' "Advanced 
        Programming in the UNIX Environment" for details (ISBN 0201563177)
        http://www.erlenstar.demon.co.uk/unix/faq_2.html#SEC16
        """
        try: 
            pid = os.fork() 
            if pid > 0:
                # exit first parent
                sys.exit(0) 
        except OSError, e: 
            sys.stderr.write("fork #1 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1)
    
        # decouple from parent environment
        os.chdir("/") 
        os.setsid() 
        os.umask(0) 
    
        # do second fork
        try: 
            pid = os.fork() 
            if pid > 0:
                # exit from second parent
                sys.exit(0) 
        except OSError, e: 
            sys.stderr.write("fork #2 failed: %d (%s)\n" % (e.errno, e.strerror))
            sys.exit(1) 
    
        # redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        si = file(self.stdin, 'r')
        so = file(self.stdout, 'a+')
        se = file(self.stderr, 'a+', 0)
        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())
    
        # write pidfile
        atexit.register(self.delpid)
        pid = str(os.getpid())
        file(self.pidfile,'w+').write("%s\n" % pid)
    
    def delpid(self):
        os.remove(self.pidfile)

    def start(self):
        """
        Start the daemon
        """
        # Check for a pidfile to see if the daemon already runs
        try:
            pf = file(self.pidfile,'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None
    
        if pid:
            message = "pidfile %s already exist. Daemon already running?\n"
            sys.stderr.write(message % self.pidfile)
            sys.exit(1)
        
        # Start the daemon
        self.daemonize()
        self.run()


    def reload(self):
        pid = self.pid()
        if not pid: return
        os.kill(pid, SIGHUP)

    def pid(self):
        # Get the pid from the pidfile
        try:
            pf = file(self.pidfile,'r')
            pid = int(pf.read().strip())
            pf.close()
        except IOError:
            pid = None
    
        if not pid:
            message = "pidfile %s does not exist. Daemon not running?\n"
            sys.stderr.write(message % self.pidfile)

        return pid # not an error in a restart


    def stop(self):
        """
        Stop the daemon
        """
        # Try killing the daemon process    
        pid = self.pid()
        if not pid: return

        try:
            while 1:
                os.kill(pid, SIGTERM)
                time.sleep(0.1)
        except OSError, err:
            err = str(err)
            if err.find("No such process") > 0:
                if os.path.exists(self.pidfile):
                    os.remove(self.pidfile)
            else:
                print str(err)
                sys.exit(1)

    def restart(self):
        """
        Restart the daemon
        """
        self.stop()
        self.start()

    def run(self):
        """
        You should override this method when you subclass Daemon. It will be called after the process has been
        daemonized by start() or restart().
        """


def getmacid():
    """
      Get MAC id
    """
    return uuid.getnode()

def getserial():
    """
      Return serial number of RaspPi
    """
    # Extract serial from cpuinfo file
    cpuserial = "ERROR000000000"
    try:
      f = open('/proc/cpuinfo','r')
      for line in f:
        if line[0:6]=='Serial':
          cpuserial = line[10:26]
          break
      f.close()
    except:
      pass
    return cpuserial

def getpassword():
    """
      Get password, which is a combination of mac id and serial number
    """
    return str(hashlib.sha1(str(getmacid()) + getserial()).hexdigest())

def blink_leds():
    """
      Blink the leds on the RPi
    """
    try:
        import RPi.GPIO as GPIO
    except:
        raise Exception("Only available ON Raspberry Pi")

    def _f(t):
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        # set up GPIO output channel
        GPIO.setup(16, GPIO.OUT)
        
        while t.is_set():
            GPIO.output(16, GPIO.LOW)
            time.sleep(0.4)
            GPIO.output(16, GPIO.HIGH)
            time.sleep(0.4)

    o = threading.Event()
    o.set()
    t = threading.Thread(target=_f, args=(o,))
    t.start()
    return t, o
      
def stop_blinking(v):
    """
      stop blinking the leds
    """
    t, o = v 
    o.clear()
    t.join()

