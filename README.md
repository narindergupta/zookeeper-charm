# zookeeper-charm

This charm will use deb package from Ubuntu private PPA.

# Building

    cd src
    charm build

Will build the zookeeper charm in `/tmp/charm-builds/zookeeper`.

# Operating

This charm require the private ppa configuration. It relates to zookeeper and
scales horizontally by adding units.

    juju deploy /tmp/charm-builds/zookeeper
    juju deploy zookeeper

# Notes

The zookeepr charm will deploy zookeeper application.

# Details

Much of the charm implementation is borrowed from the Apache zookeeper
charm, but it's been heavily simplified and pared down. Jinja templating is
used instead of Puppet, and a few helper functions that were imported from
libraries are inlined.

---
