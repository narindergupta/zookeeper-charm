import os
import shutil

from charmhelpers.core import hookenv

from charms.reactive import when, when_not, hook, set_state, remove_state


@when('local-monitors.available')
def local_monitors_available(nagios):
    setup_nagios(nagios)


@when('nrpe-external-master.available')
def nrpe_external_master_available(nagios):
    setup_nagios(nagios)


def setup_nagios(nagios):
    config = hookenv.config()
    unit_name = hookenv.local_unit()
    checks = [{
        'name': 'zk_open_file_descriptor_coun',
        'description': 'ZK_Open_File_Descriptors_Count',
        'warn': 500,
        'crit': 800,
    }, {
        'name': 'zk_ephemerals_count',
        'description': 'ZK_Ephemerals_Count',
        'warn': 10000,
        'crit': 100000,
    }, {
        'name': 'zk_avg_latency',
        'description': 'ZK_Avg_Latency',
        'warn': 500,
        'crit': 1000,
    }, {
        'name': 'zk_max_latency',
        'description': 'ZK_Max_Latency',
        'warn': 2000,
        'crit': 3000,
    }, {
        'name': 'zk_min_latency',
        'description': 'ZK_Min_Latency',
        'warn': 500,
        'crit': 1000,
    }, {
        'name': 'zk_outstanding_requests',
        'description': 'ZK_Outstanding_Requests',
        'warn': 20,
        'crit': 50,
    }, {
        'name': 'zk_watch_count',
        'description': 'ZK_Watch_Count',
        'warn': 100,
        'crit': 500,
    }]
    check_cmd = ['/usr/local/lib/nagios/plugins/check_zookeeper.py',
                 '-o', 'nagios',
                 '-s', '{}:2181'.format(hookenv.unit_private_ip())]
    for check in checks:
        nagios.add_check(check_cmd + ['--key', check['name'],
                                      '-w', str(check['warn']),
                                      '-c', str(check['crit'])],
                         name=check['name'],
                         description=check['description'],
                         context=config["nagios_context"],
                         servicegroups=(config.get("nagios_servicegroups")
                                        or config["nagios_context"]),
                         unit=unit_name)
    nagios.updated()
    set_state('zookeeper.nrpe_helper.registered')


@hook('upgrade-charm')
def nrpe_helper_upgrade_charm():
    # Make sure the nrpe handler will get replaced at charm upgrade
    remove_state('zookeeper.nrpe_helper.installed')


@when('zookeeper.nrpe_helper.registered')
@when_not('zookeeper.nrpe_helper.installed')
def install_nrpe_helper():
    dst_dir = '/usr/local/lib/nagios/plugins/'
    if not os.path.exists(dst_dir):
        os.makedirs(dst_dir)
    src = '{}/files/check_zookeeper.py'.format(hookenv.charm_dir())
    dst = '{}/check_zookeeper.py'.format(dst_dir)
    shutil.copy(src, dst)
    os.chmod(dst, 0o755)
    set_state('zookeeper.nrpe_helper.installed')
