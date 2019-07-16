from charmhelpers.core import hookenv

from charms.reactive import hook

from charms import apt


@hook('stop')
def uninstall():
    try:
        apt.purge('zookeeper')
    except Exception as e:
        # log errors but do not fail stop hook
        hookenv.log('failed to remove zookeeper: {}'.format(e), hookenv.ERROR)
