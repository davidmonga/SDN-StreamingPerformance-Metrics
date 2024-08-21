from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel
import time
import subprocess
import matplotlib.pyplot as plt
from openpyxl import Workbook

class DataTrafficInput:
    def __init__(self):
        self._servers = ['h1', 'h3']
        self._clients = ['h2', 'h4']
        self._PERTURBATION_NUMBERS = [12, 10, 8]  # Configurations de bande passante (en Mbps)
        self._ports = [5000, 6000]

    def get_servers(self):
        return self._servers

    def get_clients(self):
        return self._clients

    def get_perturbation_numbers(self):
        return self._PERTURBATION_NUMBERS

    def get_ports(self):
        return self._ports

class NetworkTopology(Topo):
    def build(self):
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')
        self.addHost('h1', mac="00:00:00:00:00:01", ip="10.1.1.1/24")
        self.addHost('h2', mac="00:00:00:00:00:02", ip="10.1.1.2/24")
        self.addHost('h3', mac="00:00:00:00:00:03", ip="10.1.1.3/24")
        self.addHost('h4', mac="00:00:00:00:00:04", ip="10.1.1.4/24")
        self.addLink(s1, s2, cls=TCLink, bw=10, use_htb=True)
        self.addLink('h1', s1, cls=TCLink, bw=10, use_htb=True)
        self.addLink('h2', s2, cls=TCLink, bw=10, use_htb=True)
        self.addLink('h3', s1, cls=TCLink, bw=10, use_htb=True)
        self.addLink('h4', s2, cls=TCLink, bw=10, use_htb=True)

class IperfTrafficClient:
    @staticmethod
    def run_traffic(server, client, port, bw):
        bande = bw    
        server.cmd(f'iperf -u -s -p {port} -i 10 -t 30 > {server.name}_server_{bw}.log &')
        client.cmd(f'iperf -u -c {server.IP()} -p {port} -b {bande}M -i 10 -t 30 > {client.name}_client_{bw}.log &')

class ExcelSaver:
    @staticmethod
    def save_bandwidth_results(bw_data):
        workbook = Workbook()
        sheet = workbook.active
        sheet.append(["Configured Bandwidth (Mo)", "Measured Bandwidth (Mo)"])
        for bw, measured_bw in bw_data.items():
            sheet.append([bw, measured_bw])
        workbook.save("bandwidth_results.xlsx")

    @staticmethod
    def plot_bandwidth_results(bw_data):
        plt.figure()
        plt.plot(list(bw_data.keys()), list(bw_data.values()), marker='o')
        plt.title("Measured Bandwidth vs Configured Bandwidth")
        plt.xlabel("Configured Bandwidth (Mo)")
        plt.ylabel("Measured Bandwidth (Mo)")
        plt.grid(True)
        plt.savefig("bandwidth_results.png")
        plt.show()

class Main:
    @staticmethod
    def main():
        setLogLevel('info')
        traffic_input = DataTrafficInput()
        net = Mininet(topo=NetworkTopology(), switch=OVSKernelSwitch, link=TCLink, controller=None)  # Désactiver l'ajout du contrôleur
        net.start()

        servers = traffic_input.get_servers()
        clients = traffic_input.get_clients()
        ports = traffic_input.get_ports()
        PERTURBATION_NUMBERS = traffic_input.get_perturbation_numbers()

        bw_results = {}
        for bw in PERTURBATION_NUMBERS:
            print(f"Testing with bandwidth: {bw} Mbps \n")
            net.configLinkStatus('s1', 's2', 'down')
            net.addLink('s1', 's2', cls=TCLink, bw=bw, use_htb=True)
            net.configLinkStatus('s1', 's2', 'up')

            # Affichage des configurations QoS et des queues OVS après modification
            #subprocess.run(["sudo", "ovs-vsctl", "list", "qos"])
            #subprocess.run(["sudo", "ovs-vsctl", "list", "queue"])

            for i in range(len(servers)):
                server = net.get(servers[i])
                client = net.get(clients[i])
                IperfTrafficClient.run_traffic(server, client, ports[i], bw)

            time.sleep(40)  # wait for the iperf tests to finish
            measured_bw = Main.parse_bandwidth_result(f"{client.name}_client_{bw}.log", bw)
            bw_results[bw] = measured_bw

        ExcelSaver.save_bandwidth_results(bw_results)
        ExcelSaver.plot_bandwidth_results(bw_results)

        CLI(net)
        net.stop()

    @staticmethod
    def parse_bandwidth_result(log_file, bw):
        with open(log_file, 'r') as file:
            lines = file.readlines()
            for line in lines:
                if "Mbits/sec" in line:
                    return float(line.split()[-2])  # extract bandwidth value
        return 0.0

if __name__ == "__main__":
    Main.main()

