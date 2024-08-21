from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, in_proto, ipv4, tcp
from ryu import cfg
from ryu.app.wsgi import ControllerBase, WSGIApplication, route, Response
import json
import time
import threading

class FlowManager:
    def __init__(self, datapaths):
        self.datapaths = datapaths

    def add_flow(self, datapath, priority, match, actions, buffer_id=None, idle=0, hard=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(datapath=datapath, priority=priority,
                                idle_timeout=idle, hard_timeout=hard,
                                match=match, instructions=inst)
        datapath.send_msg(mod)

    def delete_flow(self, datapath, match):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        mod = parser.OFPFlowMod(datapath=datapath, command=ofproto.OFPFC_DELETE,
                                out_port=ofproto.OFPP_ANY, out_group=ofproto.OFPG_ANY,
                                match=match)
        datapath.send_msg(mod)

class QoS:
    def __init__(self, CONF, datapaths, logger):
        self.CONF = CONF
        self.datapaths = datapaths
        self.flow_manager = FlowManager(datapaths)
        self.logger = logger
        self.qos_flows = []  # Liste pour suivre les configurations QoS
        self._start_monitoring()  # Lance la surveillance de la bande passante

    def update_qos(self, bw, ports):
        # Met à jour la configuration QoS pour les 8 ports TCP spécifiés
        self.logger.info(f"Requête QoS reçue : bw={bw}kbps, ports={ports}, protocole=TCP")
        # Enregistre la configuration QoS pour la surveillance
        self.qos_flows.append({'bw': bw, 'ports': ports, 'protocol': 6})  # Protocole 6 = TCP

    def _start_monitoring(self):
        """Démarre un thread en arrière-plan pour surveiller les flux QoS toutes les 10 secondes."""
        def monitor():
            while True:
                for flow in self.qos_flows:
                    for port in flow['ports']:
                        usage = self._simulate_bandwidth_usage(flow)
                        if usage > flow['bw']:
                            exceeded = usage - flow['bw']
                            self.logger.info(f"Alerte QoS : Le port TCP {port} a dépassé {flow['bw']}kbps. Excès : {exceeded}kbps")
                        else:
                            self.logger.info(f"Info QoS : Le port TCP {port} respecte la limite de {flow['bw']}kbps. Utilisation : {usage}kbps")
                time.sleep(10)  # Surveille toutes les 10 secondes

        monitoring_thread = threading.Thread(target=monitor, daemon=True)
        monitoring_thread.start()

    def _simulate_bandwidth_usage(self, flow):
        """Simule l'utilisation de la bande passante pour cet exemple."""
        import random
        return random.randint(0, flow['bw'] + 100)  # Utilisation aléatoire pour le test

class Controller(app_manager.RyuApp):
    _CONTEXTS = {'wsgi': WSGIApplication}
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(Controller, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        self.CONF = cfg.CONF
        self.qos = QoS(self.CONF, self.datapaths, self.logger)
        wsgi = kwargs['wsgi']
        wsgi.register(QoSController, {'qos_api_app': self})

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        self.datapaths[datapath.id] = datapath
        self.add_default_flow(datapath)

    def add_default_flow(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.qos.flow_manager.add_flow(datapath, 0, match, actions)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dst = eth.dst
        src = eth.src

        if dst[:5] == "33:33":
            return

        dpid = datapath.id
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        match = parser.OFPMatch(in_port=in_port, eth_dst=dst)
        self.qos.flow_manager.add_flow(datapath, 1, match, actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

class QoSController(ControllerBase):
    def __init__(self, req, link, data, **config):
        super(QoSController, self).__init__(req, link, data, **config)
        self.qos_api_app = data['qos_api_app']

    @route('qos', '/qos/update', methods=['POST'])
    def update_qos(self, req, **kwargs):
        try:
            qos_data = json.loads(req.body)
            bw = qos_data['bw']
            ports = [
                qos_data['port1'], qos_data['port2'], qos_data['port3'],
                qos_data['port4'], qos_data['port5'], qos_data['port6'],
                qos_data['port7'], qos_data['port8']
            ]
            self.qos_api_app.qos.update_qos(bw, ports)
            return Response(status=200, body="QoS updated")
        except Exception as e:
            return Response(status=500, body=str(e))

