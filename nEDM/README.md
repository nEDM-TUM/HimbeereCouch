Raspberry Pis on nEDM
=====================

For simplicity, all Raspberry Pis connected to the network at the nEDM
experiment are booted via NFS.  This allows us to deploy changes of the
software to all devices very efficiently.

To install a new device, download [rasb_pi.img.gz](rasb_pi.img.gz) and flash it
to your SD card:

```sh
gunzip -c rasb_pi.img.gz | sudo dd of=/dev/sd_card
```

where `/dev/sd_card` is the correct path to the SD card.

Then, simply connect to the nEDM network.


