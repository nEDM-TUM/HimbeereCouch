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

