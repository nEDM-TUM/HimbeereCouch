import hashlib
import threading
import time

def getmacid(interface=None):
    """
      Get MAC id
    """
    if interface is None:
        interface = "eth0"
    return int(
        open('/sys/class/net/{}/address'.format(interface)).read()
        .rstrip()
        .replace(':',''), 16)

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

