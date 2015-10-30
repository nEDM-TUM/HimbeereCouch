---
title: HimbeereCouch
layout: basic
is_index: true
---

Python module for handling communication/code deployment on to the nEDM
Raspberry Pis.

## Information

`himbeerecouch` provides a daemon which obtains code from the CouchDB database
to run on a particular Raspberry Pi.  It also listens for changes and restarts
itself whenever code is updated in the central database.  Code is generally
updated on the [web interface](http://db.nedm1/page/control/nedm/raspberries).

## Installation/Upgrade:

With pip:
{% highlight bash %}
pip install [--upgrade] https://github.com/nEDM-TUM/HimbeereCouch/tarball/master#egg=himbeerecouch
{% endhighlight %}

### Requirements

1. [RPi.GPIO (optional)](https://pypi.python.org/pypi/RPi.GPIO), needed to access GPIO pins in user code.

_Note_: on the
[nEDM raspberries that Netboot]({{ site.url }}/System-Overview/subsystems/Raspberry-Pis.html), this is already installed.
See that documentation for instructions on how to update.

### Deploy on a standalone Raspberry Pi:
(Note, one can do this once on a single Raspberry Pi, and
copy the SD card for future Raspberry Pi.  If this is done, then you only need
to start from step #3.)  For the nEDM experiment, we use an NFS boot so that
the Rasp-Pis always have the same OS/software.

There are two options:

1.  (preferred) on systems with `supervisord` installed, install the following in e.g. `/etc/supervisord/conf.d/raspberry.conf`:
{% highlight ini %}
[program:raspberry]
command=python -c 'import himbeerecouch.prog as p; p.run("/etc/rspby/server")'
autostart=true
autorestart=true
stopsignal=INT
redirect_stderr=true
stdout_logfile=/var/log/rspby_daemon.log
{% endhighlight %}

or

1.  Download/install the daemon at [`init_scripts/rspby`]( {{ site.github.repository_url }}/blob/master/init_scripts/rspby ):
  1. e.g. in ```/etc/init.d```
  1. Set up folders for log/pid file/server file (default, ```/var/rspby```)
  1. Edit ```/etc/rc.d``` or relevant file to start daemon on boot

then:

2. Connect Rasp Pi to network.

Once connected, there are two options to determine which password/user name to
setup in the database:

3. (Option 1) On local machine also connected to network, run:

{% highlight python %}
>>> import himbeerecouch
>>> himbeerecouch.broadcast_message("http://server.name:5984")
# ... should return the following
{ "MacID" : 1234566, "password" : "apassword" }
{% endhighlight %}

  Sometimes this doesn't work (depending upon UDP forwarding on network).  If so, use (Option 2)

4. (Option 2) On Rasp Pi

{% highlight python %}
>>> import himbeerecouch
>>> himbeerecouch.util.getmacid()
12345678901234L
>>> himbeerecouch.util.getpassword()
'apassword'
{% endhighlight %}

Use these credentials to set up a user on CouchDB with access to the chosen
database (default `nedm/raspberries`).  (See [here]({{ site.url }}/System-Overview/sysbsystems/DB-Administration.html)
for more information.)

### Running code

#### Single module mode
The Daemon expects documents to be submitted to the database (default
`nedm/raspberries`) that look like:

{% highlight python %}
{
  "type" : MacID # This is an integer!
  "name" : "Name of code"
  "code" : "   ... python code here "
}
{% endhighlight %}

It attempts to load the code in `"code"` as a module, and runs the `main`
function in the module.  The daemon will react whenever a new document is
loaded/updated.  The code should look like:

{% highlight python %}
def main():
    # This code is executed.  It has access to the following functions:
    #     log(*args)  : logging function
    #     should_quit()  : check if this code should exit (useful for daemons)
    #     register_quit_notification(afunc)  : registers a quit notification, i.e. function 'afunc' is called when this code should exit
    #     remove_quit_notification(afunc)  : deregisters a quit notification
{% endhighlight %}

#### Multiple module mode
Note, that it is also possible to pass your code in _module_ form, for example:

{% highlight python %}
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
{% endhighlight %}

*Note*, all of these are optional.  If e.g. `"code"` is omitted and there is no `"main"` in `"modules"`, then only
`"global_modules"` will essentially have any effect as they will be exported
to other code in the database.

### Running arbitrary commands

The daemon will respond to the insertion of a document that look like:

{% highlight python %}
    {
      "type" : "MacID_cmd" # MacID is an integer in the string!
      "cmd" : [ "acommand", "flag1", "flag2" ... ]
    }
{% endhighlight %}

and update the document to be:

{% highlight python %}
    {
      "type" : "MacID_cmd" # MacID is an integer in the string!
      "cmd" : [ "acommand", "flag1", "flag2" ... ],
      "ret" : [ "return string from accomand" ]
    }
{% endhighlight %}
