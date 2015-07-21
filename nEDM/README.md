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

## Network setup

_documentation for advanced users_

By and large, the configuration of the NFS boot follows instructions available around the [web](http://blogs.wcode.org/2013/09/howto-netboot-a-raspberry-pi/).

A few points:

1.  We use the Synology [raid server](http://raid.nedm1:5000) (link will function when connected to the nEDM VPN) as our NFS mount.
2.  Our DHCP settings look like:

  ```
  class "raspberries" {
    match if ( substring(hardware,1,3) = b8:27:eb );
    default-lease-time 115200;
    option root-path "192.168.1.9:/volume1/Raspberries/boot/current,tcp,vers=3";
  }
  ```


