#!/usr/bin/env python

import argparse
import os
from ssh_paramiko import RemoteServer
import sys
import time

class UnableToConnectException(Exception):
    message = "Unable to connect to Server"

    def __init__(self, server):
        self.details = {
            "server": server,
        }
        super(UnableToConnectException, self).__init__(self.message, self.details)


class OpenshiftDeployer:
    def __init__(self):
        self.client = None
        self.save_dir = '/tmp'

    def sles_only_command(self, command):
        platform_specific="if [ -f /etc/SuSE-release ]; then {}; fi".format(command)
        return platform_specific

    def ubuntu_only_command(self, command):
        platform_specific="if [ -f /etc/lsb-release ]; then {}; fi".format(command)
        return platform_specific

    def centos_or_redhat_only_command(self, command):
        platform_specific="if [ -f /etc/centos-release -o -f /etc/redhat-release ]; then {}; fi".format(command)
        return platform_specific

    def centos_only_command(self, command):
        platform_specific="if [ -f /etc/centos-release ]; then {}; fi".format(command)
        return platform_specific

    def redhat_only_command(self, command):
        platform_specific="if [ -f /etc/redhat-release ]; then {}; fi".format(command)
        return platform_specific

    def _get_first_token(self, text):
        if len(text.split()) > 0:
	    return(text.split()[0])
        return None

    def show_step(self, step):
        """
        Simple function to print the step we are working on
        """

        sys.stdout.flush()
        print("******************************************************")
        print("* {}".format(step))
        print("******************************************************")
        sys.stdout.flush()
        return None

    def setup_arguments(self):
        parser = argparse.ArgumentParser(description='Setup OpenShift')

        # node settings
        parser.add_argument('--ip', dest='IP', action='store', nargs='*',
                        help='Space seperated list of IP addresses of the nodes')
        parser.add_argument('--username', dest='USERNAME', action='store',
                        default='root', help='Node Username, default is \"root\"')
        parser.add_argument('--password', dest='PASSWORD', action='store',
                        default='password', help='Node password, default is \"password\"')

        # openshift options
        parser.add_argument('--version', dest='VERSION', action='store', required=True,
                        help='Version to install, such as "release-3.7"')

        # misc options
        parser.add_argument('--preponly', action='store_true',
                            help='Sets up the node to run ansible but does not invoke it')

        # return the parser object
        return parser

    def connect_to_host(self, ipaddr, numTries=5):
        """
        Connect to a host
        """
        attempt=1
        connected = False

        ssh = RemoteServer(None,
                           username=self.args.USERNAME,
                           password=self.args.PASSWORD,
                           log_folder_path='/tmp',
                           server_has_dns=False)
        while (attempt<=numTries and connected==False):
            print("Connecting to: %s" % (ipaddr))

            connected, err = ssh.connect_server(ipaddr, False)
            if connected == False:
                time.sleep(5)
                attempt = attempt + 1

        if connected == False:
            raise UnableToConnectException(ipaddr)

        return ssh

    def node_execute_command(self, ipaddr, command, numTries=5):
        """
        Execute a command via ssh
        """
        ssh = self.connect_to_host(ipaddr, numTries)

        print("Executing Command: %s" % (command))
        rc, stdout, stderr = ssh.execute_cmd(command, timeout=None)
        ssh.close_connection()

        stdout.strip()
        stderr.strip()

        if rc is True:
            print("%s" % stdout)

        return rc, stdout, stderr

    def node_execute_multiple(self, ipaddr, commands):
        """
        execute a list of commands
        """
        for cmd in commands:
            rc, output, error = self.node_execute_command(ipaddr, cmd)
            if rc is False:
                print("error running: [%s] %s" % (ipaddr, cmd))

    def setup_all_nodes(self, args):
        """
        Prepare all the nodes

        Install pre-reqs
        """
        _commands = []
        prereqs="pyOpenSSL python-cryptography python-lxml java-1.8.0-openjdk-headless patch httpd-tools docker git wget"
        _commands.append(self.centos_or_redhat_only_command("yum install -y {}".format(prereqs)))
        _commands.append("systemctl enable docker")
        _commands.append("systemctl start docker")
        _commands.append("mkdir -p /usr/libexec/kubernetes/kubelet-plugins/volume/exec/dell~scaleio/")

        for ipaddr in args.IP:
            self.node_execute_multiple(ipaddr, _commands)

    def setup_master(self, ipaddr, args):
        """
        Prepare a host to setup systems

        This includes installing some pre-reqs as well as
        cloning a git repo that configures openshift with ansible
        """

        _commands = []
        # install some pre-reqs
        _commands.append(self.centos_or_redhat_only_command('(curl https://bootstrap.pypa.io/get-pip.py | python) && pip install ansible'))

        # clone the playbooks and customize them
        _commands.append('cd /; mkdir git; chmod -R 777 /git')
        _commands.append("cd /git && git clone https://github.com/openshift/openshift-ansible.git -b {}".format(args.VERSION))

        _commands.append("sed -i 's|NODE0|{}|g' /tmp/hosts.openshift".format(args.IP[0]))
        if len(args.IP) > 1:
            _commands.append("sed -i 's|#NODE1|{}|g' /tmp/hosts.openshift".format(args.IP[1]))
        if len(args.IP) > 2:
            _commands.append("sed -i 's|#NODE2|{}|g' /tmp/hosts.openshift".format(args.IP[2]))
        if len(args.IP) > 3:
            _commands.append("sed -i 's|#NODE3|{}|g' /tmp/hosts.openshift".format(args.IP[3]))
        if len(args.IP) > 4:
            _commands.append("sed -i 's|#NODE4|{}|g' /tmp/hosts.openshift".format(args.IP[4]))

        self.node_execute_multiple(ipaddr, _commands)

        if not args.preponly:
            self.node_execute_command(ipaddr,
                                      "cd /git/openshift-ansible && ansible-playbook -vv -i /tmp/hosts.openshift playbooks/byo/config.yml")
            self.node_execute_command(ipaddr, "htpasswd -b -c /etc/origin/master/htpasswd admin secret")
            self.node_execute_command(ipaddr, "htpasswd -b /etc/origin/master/htpasswd user secret")
            self.node_execute_command(ipaddr, "oc get nodes")
        else:
            print("To setup Openshift, log onto {} as root and run:".format(args.IP[0]))
            print("  \"cd /git/openshift-ansible && ansible-playbook -i /tmp/hosts.openshift playbooks/byo/config.yml\"")

    def put_files(self, ipaddr):
        """
        put some files to the node

        """

        self.show_step('Putting files')
        ssh = self.connect_to_host(ipaddr)

        ssh.put_file('{}/hosts.openshift-{}'.format(os.path.dirname(os.path.realpath(sys.argv[0])),self.args.VERSION),
                     '/tmp/hosts.openshift')
        ssh.close_connection()

    def get_files(self, ipaddr):
        """
        Copy some files to save directory

        """

        self.show_step('Getting files')
        ssh = self.connect_to_host(ipaddr)

        files = ['/etc/origin/master/admin.kubeconfig', '/tmp/hosts.openshift']
        for filename in files:
            basename=os.path.basename(filename)
            target='{}/{}'.format(self.save_dir, basename)
            ssh.get_file(target, filename)
            os.chmod(target,  0o777)

        ssh.close_connection()

    def post_setup(self, args):
        """
        Perform any post deployment setup


        """
        return

    def process(self):
        """
        Main logic
        """
        parser = self.setup_arguments()
        self.args = parser.parse_args()

        self.setup_all_nodes(self.args)
        self.put_files(self.args.IP[0])
        self.setup_master(self.args.IP[0], self.args)
        self.post_setup(self.args)
        self.get_files(self.args.IP[0])


# Start program
if __name__ == "__main__":
    deployer = OpenshiftDeployer()
    deployer.process()
