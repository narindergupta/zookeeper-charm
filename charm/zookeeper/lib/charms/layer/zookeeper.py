# Licensed to the Apache Software Foundation (ASF) under one or more
# contributor license agreements.  See the NOTICE file distributed with
# this work for additional information regarding copyright ownership.
# The ASF licenses this file to You under the Apache License, Version 2.0
# (the "License"); you may not use this file except in compliance with
# the License.  You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import subprocess

from charmhelpers.core import host, hookenv, unitdata
from charmhelpers.core.templating import render

from charms.reactive.relations import RelationBase


ZK_PORT = 2181
ZK_REST_PORT = 9998
APP_NAME = 'zookeeper'
APP_COMMON = '/etc/{}/conf'.format(APP_NAME)
SERVICE_NAME = '{name}.service'.format(name=APP_NAME)
APP_DATADIR = '/var/lib/{}'.format(APP_NAME)


def format_node(unit, node_ip):
    '''
    Given a juju unit name and an ip address, return a tuple
    containing an id and formatted ip string suitable for passing to
    zoo.cfg templates.

    '''
    return (unit.split("/")[1], "{ip}:2888:3888".format(ip=node_ip))


class Zookeeper(object):
    '''
    Utility class for managing Zookeeper tasks like configuration, start,
    stop, and adding and removing nodes.

    '''

    def is_zk_leader(self):
        '''
        Attempt to determine whether this node is the Zookeeper leader.

        Note that Zookeeper tracks leadership independently of juju,
        and that this command can fail, depending on the state that
        the Zookeeper node is in when we attempt to run it.

        '''
        try:
            status = subprocess.check_output(
                ["/usr/share/{}/bin/zkServer.sh".format(APP_NAME), "status"])
            return "leader" in status.decode('utf-8')
        except Exception:
            hookenv.log(
                "Unable to determine whether this node is the Zookeeper "
                "leader.",
                level="WARN"
            )
            return False

    def read_peers(self):
        '''
        Fetch the list of peers available.

        The first item in this list should always be the node that
        this code is executing on.

        '''
        # A Zookeeper node likes to be first on the list.
        nodes = [(hookenv.local_unit(), hookenv.unit_private_ip())]
        # Get the list of peers
        zkpeer = RelationBase.from_state('zkpeer.joined')
        if zkpeer:
            nodes.extend(sorted(zkpeer.get_nodes()))
        nodes = [format_node(*node) for node in nodes]
        return nodes

    def sort_peers(self, zkpeer):
        '''
        Return peers, sorted in an order suitable for performing a rolling
        restart.

        '''
        peers = self.read_peers()
        leader = zkpeer.find_zk_leader()
        peers.sort(key=lambda x: x[1] == leader)

        return peers

    def install(self, nodes=None):
        '''
        Write out the config, then restart services.

        After this runs, we should have a configured and running service.
        '''
        cfg = hookenv.config()
        myid = hookenv.local_unit().split('/')[1]
        datadir = unitdata.kv().get('zookeeper.storage.data_dir',
                                    os.path.join(APP_DATADIR))
        os.makedirs(datadir, exist_ok=True)
        render(
            source="zoo.cfg",
            target=os.path.join(APP_COMMON, 'zoo.cfg'),
            owner='root',
            perms=0o644,
            context={
                'myid': myid,
                'datadir': datadir,
                'ensemble': self.read_peers(),
                'client_bind_addr': hookenv.unit_private_ip(),
                'port': ZK_PORT,
                'autopurge_purge_interval': cfg.get(
                    'autopurge_purge_interval'),
                'autopurge_snap_retain_count': cfg.get(
                    'autopurge_snap_retain_count'),
            })
        with open(os.path.join(datadir, 'myid'), 'w') as f:
            f.write(myid)
        self.restart()
        if self.is_zk_leader():
            zkpeer = RelationBase.from_state('zkpeer.joined')
            zkpeer.set_zk_leader()

    def start(self):
        '''
        Start zookeeper.

        Attempt to determine whether this node is the Zookeeper leader.

        Note that Zookeeper tracks leadership independently of juju,
        and that this command can fail, depending on the state that
        the Zookeeper node is in when we attempt to run it.

        '''
        try:
            status = subprocess.check_output(
                ["/usr/share/{}/bin/zkServer.sh".format(APP_NAME), "start"])
            return "STARTED" in status.decode('utf-8')
        except Exception:
            hookenv.log(
                "Unable to start this node as the Zookeeper "
                "leader.",
                level="WARN"
            )
            return False

    def restart(self):
        '''
        Restart zookeeper.

        '''
        try:
            status = subprocess.check_output(
                ["/usr/share/{}/bin/zkServer.sh".format(APP_NAME), "restart"])
            return "STARTED" in status.decode('utf-8')
        except Exception:
            hookenv.log(
                "Unable to restart this node is the Zookeeper "
                "leader.",
                level="WARN"
            )
            return False

    def stop(self):
        '''
        Stop zookeeper.

        '''
        try:
            status = subprocess.check_output(
                ["/usr/share/{}/bin/zkServer.sh".format(APP_NAME), "stop"])
            return "STOPPED" in status.decode('utf-8')
        except Exception:
            hookenv.log(
                "Unable to stop this node"
                "leader.",
                level="WARN"
            )
            return False

    def is_running(self):
        try:
            status = subprocess.check_output(
                ["/usr/share/{}/bin/zkServer.sh".format(APP_NAME), "status"])
            return ("follower" in status.decode('utf-8') or
                   "standalone" in status.decode('utf-8') or
                   "leader" in status.decode('utf-8'))
        except Exception:
            hookenv.log(
                "Unable to determine whether this node is the Zookeeper "
                "leader.",
                level="WARN"
            )
            return False

    def open_ports(self):
        '''
        Expose the ports in the configuration to the outside world.

        '''
        hookenv.open_port(ZK_PORT)

    def close_ports(self):
        '''
        Close off communication from the outside world.

        '''
        hookenv.close_port(ZK_PORT)

    def quorum_check(self):
        '''
        Returns a string reporting the node count. Append a message
        informing the user if the node count is too low for good quorum,
        or is even (meaning that one of the nodes is redundant for
        quorum).

        '''
        node_count = len(self.read_peers())
        if node_count == 1:
            count_str = "{} unit".format(node_count)
        else:
            count_str = "{} units".format(node_count)
        if node_count < 3:
            return " ({}; less than 3 is suboptimal)".format(count_str)
        if node_count % 2 == 0:
            return " ({}; an even number is suboptimal)".format(count_str)
        return "({})".format(count_str)
