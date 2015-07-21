HimbeereCouch
=============

himbeerecouch provides a module for automatically running python software
stored in a CouchDB instance on a Raspberry Pi.  A light daemon runs on a
Raspberry Pi (with any general Raspberry Pi distribution) and listens to the
changes feed from a defined CouchDB database.  When new code is uploaded or old
code is changed, the daemon automatically restarts the python code running on
its instance.

Separate Rasp Pis are differentiated by their MAC addresses.

# Get up and running:

## Requirements on the Raspberry Pi:

1. [pip](https://pypi.python.org/pypi/pip)
2. [RPi.GPIO (optional)](https://pypi.python.org/pypi/RPi.GPIO), needed to access GPIO pins in user code.

##Basic instructions:
(Note, one can do this once on a single Raspberry Pi, and
copy the SD card for future Raspberry Pi.  If this is done, then you only need
to start from step #3.)  For the nEDM experiment, we use an NFS boot so that
the Rasp-Pis always have the same OS/software.  For more information about
this, see [nEDM](nEDM).

1.  Download/install the daemon at `init_scripts/rspby`:
  1. e.g. in ```/etc/init.d```
  1. Set up folders for log/pid file/server file (default, ```/var/rspby```)
  1. Install himbeerecouch: ```/etc/init.d/rspby install```
  1. Edit ```/etc/rc.d``` or relevant file to start daemon on boot
2. Connect Rasp Pi to network.
3. (Option 1) On local machine also connected to network, run:

    ```python
        % python
        >>> import himbeerecouch
        >>> himbeerecouch.broadcast_message("http://server.name:5984")
        # ... should return the following
        { "MacID" : 1234566, "password" : "apassword" }
    ```

  Sometimes this doesn't work (depending upon UDP forwarding on network).  If so, use (Option 2)

4. (Option 2) On Rasp Pi

    ```python
        % python
        >>> import himbeerecouch
        >>> himbeerecouch.util.getmacid()
        12345678901234L
        >>> himbeerecouch.util.getpassword()
        'apassword'
   ```
5. Use these credentials to set up a user on CouchDB with read access to the chosen database (default ```nedm/raspberries```)

## In CouchDB
### Running code

#### Single module mode
The Daemon expects documents that look like:

```python
    {
      "type" : MacID # This is an integer!
      "name" : "Name of code"
      "code" : "   ... python code here "
    }
```

It attempts to load the code as a module, and runs the ```main``` function in
the module.  The daemon will react whenever a new document is loaded/updated.
The code should look like:

 ```python
 def main():
     # This code is executed.  It has access to the following functions:
     #     log(*args)  : logging function
     #     should_quit()  : check if this code should exit (useful for daemons)
     #     register_quit_notification(afunc)  : registers a quit notification, i.e. function 'afunc' is called when this code should exit
     #     remove_quit_notification(afunc)  : deregisters a quit notification
```

#### Multiple module mode
Note, that it is also possible to pass your code in _module_ form, for example:

```python
    {
      "type" : "macid_of_rasperry<int>", # i.e. value returned by getmacid()
      "name" : "name of the code",
      "modules" : { # these are modules used by this local code
        "name_of_module1" : "<python code>",
        "name_of_module2" : "<python code>",
        ...
      },
      "global_modules" : { # these modules will be exported to *all*
                           # code in this database
        "name_of_global1" : "<python code>",
        "name_of_global2" : "<python code>"
      },
      "code" : "<python code>" # This is the main module, it *must* include a
                               # `main` function
    }
```

*Note*, all of these are optional.  If e.g. `"code"` is omitted and there is no `"main"` in `"modules"`, then only
`"global_modules"` will essentially have any effect as they will be exported
to other code in the database.

### Running arbitrary commands

The daemon will respond to the insertion of a document that look like:

```python
    {
      "type" : "MacID_cmd" # MacID is an integer in the string!
      "cmd" : [ "acommand", "flag1", "flag2" ... ]
    }
```

and update the document to be:

```python
    {
      "type" : "MacID_cmd" # MacID is an integer in the string!
      "cmd" : [ "acommand", "flag1", "flag2" ... ],
      "ret" : [ "return string from accomand" ]
    }
```

