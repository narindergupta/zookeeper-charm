import json
import time

from charmhelpers.core import hookenv, unitdata

from charms.reactive import (when, when_not, set_flag, hook,
                             clear_flag, is_state, is_flag_set)
from charms.reactive.helpers import data_changed

from charms import apt

from charms.layer.zookeeper import (
    APP_NAME, Zookeeper, ZK_PORT, ZK_REST_PORT)

from charms.leadership import leader_set, leader_get


@hook('config-changed')
def config_changed():
    # Remove configured flag to trigger reconfig.
    clear_flag('zookeeper.configured')


@when('apt.installed.zookeeper')
@when_not('zookeeper.configured')
def configure():
    cfg = hookenv.config()
    zookeeper = Zookeeper()
    changed = any((
        data_changed('zkpeer.nodes', zookeeper.read_peers()),
        data_changed('zk.autopurge_purge_interval',
                     cfg.get('autopurge_purge_interval')),
        data_changed('zk.autopurge_snap_retain_count',
                     cfg.get('autopurge_snap_retain_count')),
        data_changed('zk.storage.data_dir',
                     unitdata.kv().get('zookeeper.storage.data_dir')),
        data_changed('zk.jmx_port',
                     cfg.get('jmx_port')),
    ))
    if changed or is_flag_set('zookeeper.force-reconfigure'):
        zookeeper.install()
        zookeeper.open_ports()
    clear_flag('zookeeper.force-reconfigure')
    set_flag('zookeeper.started')
    set_flag('zookeeper.configured')
    hookenv.status_set('active', 'ready {}'.format(zookeeper.quorum_check()))
    # set app version string for juju status output
    zoo_version = apt.get_package_version(APP_NAME) or 'unknown'
    hookenv.application_version_set(zoo_version)


def _restart_zookeeper(msg):
    '''
    Restart Zookeeper by re-running the puppet scripts.

    '''
    hookenv.status_set('maintenance', msg)
    zookeeper = Zookeeper()
    zookeeper.install()
    hookenv.status_set('active', 'ready {}'.format(zookeeper.quorum_check()))


@when('zookeeper.started', 'zookeeper.joined')
def serve_client(client):
    client.send_port(ZK_PORT, ZK_REST_PORT)
    clear_flag('zookeeper.configured')


#
# Rolling restart -- helpers and handlers
#
# When we add or remove a Zookeeper peer, Zookeeper needs to perform a
# rolling restart of all of its peers, restarting the Zookeeper
# "leader" last.
#
# The following functions accomplish this. Here's how they all fit together:
#
# (As you read, keep in mind that one node functions as the "leader"
# in the context of Juju, and one node functions as the "leader" in
# the context of Zookeeper; these nodes may or may not be the same.)
#
# 0. Whenever the Zookeeper server starts, it attempts to determine
#    whether it is the Zookeeper leader. If so, it sets a flag on the
#    Juju peer relation data.
#
# 1. When a node is added or remove from the cluster, the Juju leader
#    runs `check_cluster`, and generates a "restart queue" comprising
#    nodes in the cluster, with the Zookeeper lead node sorted last in
#    the queue. It also sets a nonce, to identify this restart queue
#    uniquely, and thus handle the situation where another node is
#    added or restarted while we're still reacting to the first node's
#    addition or removal. The leader drops the queue and nonce into
#    the leadership data as "restart_queue" and "restart_nonce",
#    respectively.
#
# 2. When any node detects a leadership.changed.restart_queue event,
#    it runs `restart_for_quorum`, which is a noop unless the node's
#    private address is the first element of the restart queue. In
#    that case, if the node is the Juju leader, it will restart, then
#    remove itself from the restart queue, triggering another
#    leadership.changed.restart_queue event. If the node isn't the
#    Juju leader, it will restart itself, then run `inform_restart`.
#
# 3. `inform_restart` will create a relation data changed event, which
#    triggers `update_restart_queue` to run on the leader. This method
#    will update the restart_queue, clearing any nodes that have
#    restarted for the current nonce, and looping us back to step 2.
#
# 4. Once all the nodes have restarted, we should be in the following state:
#
#    * All nodes have an updated Zookeeper server running with the new
#    * peer data.
#
#    * The Zookeeper leader has restarted last, which should help
#      prevent orphaned jobs, per the Zookeeper docs.
#
#    * peers still have zkpeer.restarted.<nonce> set on their relation
#      data. This is okay, as we will generate a new nonce next time,
#      and the data is small.
#
# Edge cases and potential bugs:
#
# 1. Juju leader changes in the middle of a restart: this gets a
#    little bit dicey, but it should work. The new leader should run
#    `check_cluster_departed`, and start a new restart_queue.
#

def _ip_list(nodes):
    '''
    Given a list of nodes, in the format that our peer relation or
    zookeeper lib will typically return node lists in, make a list of
    just the ips (stripping ports, if they have been added).

    We expect the list we passed in to look something like this:

        [('zookeeper/0', '10.0.0.4'), ('zookeeper/1', '10.0.0.5')]

    or this:

        [('0', '10.0.0.4:2888:4888'), ('1', '10.0.0.5:2888:4888')]

    We will return a list in the form:

        ['10.0.0.4', '10.0.0.5']

    '''
    return [node[1].split(':')[0] for node in nodes]


@when('zookeeper.started', 'leadership.is_leader', 'zkpeer.joined')
@when_not('zkpeer.departed')
def check_cluster(zkpeer):
    '''
    Checkup on the state of the cluster. Start a rolling restart if
    the peers have changed.

    '''
    zk = Zookeeper()
    if data_changed('zkpeer.nodes', zk.read_peers()):
        peers = _ip_list(zk.sort_peers(zkpeer))
        nonce = time.time()
        hookenv.log('Quorum changed. Restart queue: {}'.format(peers))
        leader_set(
            restart_queue=json.dumps(peers),
            restart_nonce=json.dumps(nonce)
        )


@when('zookeeper.started', 'leadership.is_leader', 'zkpeer.joined',
      'zkpeer.departed')
def check_cluster_departed(zkpeer, zkpeer_departed):
    '''
    Wrapper around check_cluster.

    Together with check_cluster, implements the following logic:

    "Run this when zkpeer.joined and zkpeer departed, or zkpeer.joined
    and not zkpeer.departed"

    '''
    check_cluster(zkpeer)


@when('zookeeper.started', 'leadership.is_leader', 'zkpeer.changed')
def check_cluster_changed(zkpeer):
    check_cluster(zkpeer)
    # zkpeer.dismiss_changed can break under some conditions; better to just
    # remove the state directly. See
    # https://github.com/juju-solutions/interface-zookeeper-quorum/issues/9
    # for details.
    clear_flag('zkpeer.changed')


@when('leadership.changed.restart_queue', 'zkpeer.joined')
def restart_for_quorum(zkpeer):
    '''
    If we're the next node in the restart queue, restart, and then
    inform the leader that we've restarted. (If we are the leader,
    remove ourselves from the queue, and update the leadership data.)

    '''
    private_address = hookenv.unit_get('private-address')
    queue = json.loads(leader_get('restart_queue') or '[]')

    if not queue:
        # Everything has restarted.
        return

    if private_address == queue[0]:
        # It's our turn to restart.
        _restart_zookeeper('rolling restart for quorum update')
        if is_state('leadership.is_leader'):
            queue = queue[1:]
            hookenv.log('Leader updating restart queue: {}'.format(queue))
            leader_set(restart_queue=json.dumps(queue))
        else:
            zkpeer.inform_restart()


@when('leadership.is_leader', 'zkpeer.joined')
def update_restart_queue(zkpeer):
    '''
    If a Zookeeper node has restarted as part of a rolling restart,
    pop it off of the queue.

    '''
    queue = json.loads(leader_get('restart_queue') or '[]')
    if not queue:
        return

    restarted_nodes = _ip_list(zkpeer.restarted_nodes())
    new_queue = [node for node in queue if node not in restarted_nodes]

    if new_queue != queue:
        hookenv.log('Leader updating restart queue: {}'.format(queue))
        leader_set(restart_queue=json.dumps(new_queue))
