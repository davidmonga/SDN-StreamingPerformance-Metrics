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
        self._PERTURBATION_NUMBERS = [0, 3, 5, 7, 10, 50]  # Configurations de % de perte de paquets (en %)
        self._ports = [5000, 6000]
        self._nom_interface_attendus = ["h2-eth0", "h4-eth0"]

    def get_servers(self):
        return self._servers

    def get_clients(self):
        return self._clients

    def get_perturbation_numbers(self):
        return self._PERTURBATION_NUMBERS

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
        self.addLink(s1, s2, cls=TCLink, bw=16, loss=0, use_htb=True)
        self.addLink('h1', s1, cls=TCLink, bw=16, loss=0, use_htb=True)
        self.addLink('h2', s2, cls=TCLink, bw=16, loss=0, use_htb=True)
        self.addLink('h3', s1, cls=TCLink, bw=16, loss=0, use_htb=True)
        self.addLink('h4', s2, cls=TCLink, bw=16, loss=0, use_htb=True)

class IperfTrafficClient:
    @staticmethod
    def run_traffic(server, client, port, loss, nom_interface_attendu):
    
        # Configurer la perte de paquets avec tc sur l'interface spécifiée
        client.cmd(f'tc qdisc add dev {nom_interface_attendu} root netem loss {loss}%')
        
        # Lancer le serveur iperf
        server.cmd(f'iperf -u -s -p {port} -i 10 -t 30 > {server.name}_server_{loss}.log &')
        
        # Lancer le client iperf  pour avoir le trafic en présence de la perte de paquets en cours sur l'interface
        client.cmd(f'iperf -u -c {server.IP()} -p {port} -i 10 -t 30 > {client.name}_client_{loss}.log &')
        
        # Attendre que la commande iperf se termine
        #client.cmd('wait')
        time.sleep(20)
        
        # Nettoyer la configuration tc après la simulation
        client.cmd(f'tc qdisc del dev {nom_interface_attendu} root netem')


class ExcelSaver:
    @staticmethod
    def save_bandwidth_results(loss_data):
        workbook = Workbook()
        sheet = workbook.active
        # Têtes de colonne avec les paires d'hôtes
        sheet.append(["Test", "h1_h2 (%)", "h3_h4 (%)"])
        for test_num, loss_values in loss_data.items():
            sheet.append([f"Test {test_num}", loss_values["h1_h2"], loss_values["h3_h4"]])
        workbook.save("loss_results.xlsx")

    @staticmethod
    def plot_bandwidth_results(loss_data):
        tests = list(loss_data.keys())
        h1_h2_loss = [loss_values["h1_h2"] for loss_values in loss_data.values()]
        h3_h4_loss = [loss_values["h3_h4"] for loss_values in loss_data.values()]

        plt.figure()
        plt.plot(tests, h1_h2_loss, marker='o', label="h1_h2")
        plt.plot(tests, h3_h4_loss, marker='o', label="h3_h4")
        plt.title("Mesured Loss per Host Pair")
        plt.xlabel("Tests")
        plt.ylabel("Measured Loss (%)")
        plt.grid(True)
        plt.legend()
        plt.savefig("loss_results.png")
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

        loss_results = {}
        for i, loss in enumerate(PERTURBATION_NUMBERS):
            print(f"\n Testing with loss: {loss} % for h1-h2 and h3-h4 \n")
            net.configLinkStatus('s1', 's2', 'down')
            net.addLink('s1', 's2', cls=TCLink, loss=loss, use_htb=True)
            net.configLinkStatus('s1', 's2', 'up')

            # Informer le contrôleur de la nouvelle configuration de bande passante
            qos_loss = 16 // 2
            requests.post(f'http://127.0.0.1:8080/qos/update', json={
                "loss": qos_loss,
                "port1": 5000,
                "port2": 6000
            })

            # Test pour h1-h2
            IperfTrafficClient.run_traffic(net.get('h1'), net.get('h2'), ports[0], loss, nom_interface_attendus[0])
            # Test pour h3-h4
            IperfTrafficClient.run_traffic(net.get('h3'), net.get('h4'), ports[1], loss, nom_interface_attendus[1])

            time.sleep(40)  # attendre la fin des tests iperf

            loss_results[f"Test {i+1}"] = {
                "h1_h2": Main.parse_packet_loss_result(f"h2_client_{loss}.log", loss),
                "h3_h4": Main.parse_packet_loss_result(f"h4_client_{loss}.log", loss)
            }

        ExcelSaver.save_bandwidth_results(loss_results)
        ExcelSaver.plot_bandwidth_results(loss_results)

        CLI(net)
        net.stop()

    @staticmethod
    def parse_packet_loss_result(log_file,loss):
        with open(log_file, 'r') as file:
            lines = file.readlines()
            for line in lines:
                if "%" in line:
                    # Extraire la valeur du pourcentage de perte
                    return float(line.split('(')[-1].replace('%', '').replace(')', ''))
        return 0.0

if __name__ == "__main__":
    Main.main()

