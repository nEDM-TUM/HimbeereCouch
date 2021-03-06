import sys, os, time, atexit
from signal import SIGTERM, SIGHUP
from .log import set_logging_file

"""
  From: http://www.jejik.com/articles/2007/02/a_simple_unix_linux_daemon_in_python/
  Author: Sander Marechal
"""

class ForceRestart(Exception):
    """
    Exception thrown to request a full restart
    """

class Daemon:
    """
    A generic daemon class.

    Usage: subclass the Daemon class and override the run() method
    """
    def __init__(self, pidfile, stdout='/dev/null', stderr='/dev/null'):
        self.stdin = '/dev/null'
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
            sys.stderr.write("fork #1 failed: {} ({})\n".format(e.errno, e.strerror))
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
            sys.stderr.write("fork #2 failed: {} ({})\n".format(e.errno, e.strerror))
            sys.exit(1)

        # redirect standard file descriptors
        sys.stdout.flush()
        sys.stderr.flush()
        si = file(self.stdin, 'r')
        so = file("/dev/null", 'a+')
        se = file("/dev/null", 'a+', 0)
        os.dup2(si.fileno(), sys.stdin.fileno())
        os.dup2(so.fileno(), sys.stdout.fileno())
        os.dup2(se.fileno(), sys.stderr.fileno())
        set_logging_file(self.stdout)

        # write pidfile
        atexit.register(self.delpid)
        pid = str(os.getpid())
        file(self.pidfile,'w+').write("{}\n".format(pid))

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
            message = "pidfile {} already exists. Daemon already running?\n"
            sys.stderr.write(message.format(self.pidfile))
            sys.exit(1)

        # Start the daemon
        self.daemonize()
        try:
            self.run()
        except ForceRestart:
            # Forcing a restart if it was requested
            self.delpid()
            os.execl("/etc/init.d/rspby", "/etc/init.d/rspby", "start")


    def reload(self, use_this_pid = False):
        pid = os.getpid()
        if not use_this_pid:
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
            message = "pidfile {} does not exist. Daemon not running?\n"
            sys.stderr.write(message.format(self.pidfile))

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



