from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import OVSKernelSwitch, RemoteController
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel
import time
import subprocess
import requests  # Pour envoyer des requêtes au contrôleur
import matplotlib.pyplot as plt
from openpyxl import Workbook

class DataTrafficInput:
    def __init__(self):
        self._servers = ['h1', 'h3']
        self._clients = ['h2', 'h4']
        #self._PERTURBATION_NUMBERS = [8, 10, 16]  # Configurations delay en ms de perte de paquets (en ms)
        self._PERTURBATION_NUMBERS = [20, 50, 100, 200, 500, 1000]  # Configurations delay en ms de perte de paquets (en ms)
        self._JITTERS_NUMBERS = [2, 5, 10, 20, 50, 100]
        self._ports = [5000, 6000]
        self._nom_interface_attendus = ["h2-eth0", "h4-eth0"]

    def get_servers(self):
        return self._servers

    def get_clients(self):
        return self._clients

    def get_perturbation_numbers(self):
        return self._PERTURBATION_NUMBERS

    def get_jitters_numbers(self):
        return self._JITTERS_NUMBERS

    def get_ports(self):
        return self._ports
        
    def get_nom_interface_attendus(self):
        return self._nom_interface_attendus        

class NetworkTopology(Topo):
    def build(self):
        s1 = self.addSwitch('s1')
        s2 = self.addSwitch('s2')
        self.addHost('h1', mac="00:00:00:00:00:01", ip="10.1.1.1/24")
        self.addHost('h2', mac="00:00:00:00:00:02", ip="10.1.1.2/24")
        self.addHost('h3', mac="00:00:00:00:00:03", ip="10.1.1.3/24")
        self.addHost('h4', mac="00:00:00:00:00:04", ip="10.1.1.4/24")
        self.addLink(s1, s2, cls=TCLink, bw=16, delay=0, use_htb=True)
        self.addLink('h1', s1, cls=TCLink, bw=16, delay=0, use_htb=True)
        self.addLink('h2', s2, cls=TCLink, bw=16, delay=0, use_htb=True)
        self.addLink('h3', s1, cls=TCLink, bw=16, delay=0, use_htb=True)
        self.addLink('h4', s2, cls=TCLink, bw=16, delay=0, use_htb=True)

class IperfTrafficClient:
    @staticmethod
    def run_traffic(server, client, port, delay, jitter, nom_interface_attendu):
        # Configurer le délai et le jitter avec tc sur l'interface spécifiée
        # delay : délai de base
        # jitter : variation du délai
        client.cmd(f'tc qdisc add dev {nom_interface_attendu} root netem delay {delay}ms {jitter}ms distribution normal')
        
        # Lancer le serveur iperf
        server.cmd(f'iperf -u -s -p {port} -i 10 -t 30 > {server.name}_server_{delay}_{jitter}.log &')
        
        # Lancer le client iperf pour générer du trafic en présence de jitter et de délai variable
        client.cmd(f'iperf -u -c {server.IP()} -p {port} -i 10 -t 30 > {client.name}_client_{delay}_{jitter}.log &')
        
        # Attendre que la commande iperf se termine
        client.cmd('wait')
        
        # Nettoyer la configuration tc après la simulation
        client.cmd(f'tc qdisc del dev {nom_interface_attendu} root netem')



class ExcelSaver:
    @staticmethod
    def save_jitter_results(delay_data):
        workbook = Workbook()
        sheet = workbook.active
        # Têtes de colonne avec les paires d'hôtes
        sheet.append(["Test", "h1_h2 (ms)", "h3_h4 (ms)"])
        for test_num, delay_values in delay_data.items():
            sheet.append([f"Test {test_num}", delay_values["h1_h2"], delay_values["h3_h4"]])
        workbook.save("delay_results.xlsx")

    @staticmethod
    def plot_jitter_results(delay_data):
        tests = list(delay_data.keys())
        h1_h2_delay = [delay_values["h1_h2"] for delay_values in delay_data.values()]
        h3_h4_delay = [delay_values["h3_h4"] for delay_values in delay_data.values()]

        plt.figure()
        plt.plot(tests, h1_h2_delay, marker='o', label="h1_h2")
        plt.plot(tests, h3_h4_delay, marker='o', label="h3_h4")
        plt.title("Measured Delay per Host Pair")
        plt.xlabel("Tests")
        plt.ylabel("Measured Delay (ms)")
        plt.grid(True)
        plt.legend()
        plt.savefig("delay_results.png")
        plt.show()


class Main:
    @staticmethod
    def main():
        setLogLevel('info')
        traffic_input = DataTrafficInput()
        ryu_controller = RemoteController('c0', ip='127.0.0.1', port=6653)

        net = Mininet(topo=NetworkTopology(), switch=OVSKernelSwitch, link=TCLink, controller=ryu_controller)
        net.start()        

        servers = traffic_input.get_servers()
        clients = traffic_input.get_clients()
        ports = traffic_input.get_ports()
        PERTURBATION_NUMBERS = traffic_input.get_perturbation_numbers()
        nom_interface_attendus = traffic_input.get_nom_interface_attendus()
        jitters = traffic_input.get_jitters_numbers()

        delay_results = {}
        for i, delay in enumerate(PERTURBATION_NUMBERS):
            jitter = jitters[i]        
            print(f"\n Testing with delay: {delay} ms et jitter: {jitter} for h1-h2 and h3-h4 \n")
            net.configLinkStatus('s1', 's2', 'down')
            #net.addLink('s1', 's2', cls=TCLink, delay=delay, use_htb=True)
            net.addLink('s1', 's2', cls=TCLink, delay=f'{delay}ms', jitter=f'{jitter}ms', use_htb=True)

            net.configLinkStatus('s1', 's2', 'up')


            # Informer le contrôleur de la nouvelle configuration de bande passante
            qos_delay = 16 // 2
            requests.post(f'http://127.0.0.1:8080/qos/update', json={
                "delay": qos_delay,
                "port1": 5000,
                "port2": 6000
            })

            # Test pour h1-h2
            IperfTrafficClient.run_traffic(net.get('h1'), net.get('h2'), ports[0], delay, jitter, nom_interface_attendus[0])
            # Test pour h3-h4
            IperfTrafficClient.run_traffic(net.get('h3'), net.get('h4'), ports[1], delay, jitter, nom_interface_attendus[1])

            time.sleep(40)  # attendre la fin des tests iperf

            delay_results[f"Test {i+1}"] = {
                "h1_h2": Main.parse_jitter_result(f"h2_client_{delay}_{jitter}.log"),
                "h3_h4": Main.parse_jitter_result(f"h4_client_{delay}_{jitter}.log")
            }

        ExcelSaver.save_jitter_results(delay_results)
        ExcelSaver.plot_jitter_results(delay_results)

        CLI(net)
        net.stop()
        
    @staticmethod
    def parse_jitter_result(log_file):
        with open(log_file, 'r') as file:
            lines = file.readlines()
            for line in lines:
                if "Jitter" in line or "ms" in line:
                    # Extract the jitter value in ms
                    try:
                        jitter_value = float(line.split()[8])  # Jitter is typically in the 9th position (index 8)
                        return jitter_value
                    except (ValueError, IndexError):
                        continue
        return 0.0

if __name__ == "__main__":
    Main.main()

