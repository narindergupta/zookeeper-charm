from charmhelpers.core import hookenv

from charms.reactive import when

from charms.layer.zookeeper import Zookeeper


@when('zookeeper.started')
def autostart_service():
    '''
    Attempt to restart the service if it is not running.

    '''
    zookeeper = Zookeeper()
    if zookeeper.is_running():
        hookenv.status_set('active',
                           'ready {}'.format(zookeeper.quorum_check()))
        return

    for i in range(3):
        hookenv.status_set('maintenance',
                           'attempting to restart zookeeper, '
                           'attempt: {}'.format(i+1))
        zookeeper.restart()
        if zookeeper.is_running():
            hookenv.status_set('active',
                               'ready {}'.format(zookeeper.quorum_check()))
            return

    hookenv.status_set('blocked', 'failed to start zookeeper; check syslog')
