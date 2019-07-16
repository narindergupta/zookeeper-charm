import os

from charmhelpers.core import hookenv, unitdata

from charms.reactive import hook, set_flag, clear_flag

from charms.layer.zookeeper import Zookeeper


@hook('data-storage-attached')
def storage_attach():
    storageids = hookenv.storage_list('data')
    if not storageids:
        hookenv.status_set('blocked', 'cannot locate attached storage')
        return
    storageid = storageids[0]

    mount = hookenv.storage_get('location', storageid)
    if not mount:
        hookenv.status_set('blocked', 'cannot locate attached storage mount')
        return

    data_dir = os.path.join(mount, "data")
    unitdata.kv().set('zookeeper.storage.data_dir', data_dir)
    hookenv.log('Zookeeper data storage attached at {}'.format(data_dir))
    # Stop Zookeeper; removing zookeeper.configured state will trigger
    # a reconfigure if/when it's ready
    zookeeper = Zookeeper()
    zookeeper.close_ports()
    zookeeper.stop()
    clear_flag('zookeeper.configured')
    hookenv.status_set('waiting', 'reconfiguring to use attached storage')
    set_flag('zookeeper.storage.data.attached')


@hook('data-storage-detaching')
def storage_detaching():
    unitdata.kv().unset('zookeeper.storage.data_dir')
    zookeeper = Zookeeper()
    zookeeper.close_ports()
    zookeeper.stop()
    clear_flag('zookeeper.configured')
    hookenv.status_set('waiting', 'reconfiguring to use temporary storage')
    clear_flag('zookeeper.storage.data.attached')
