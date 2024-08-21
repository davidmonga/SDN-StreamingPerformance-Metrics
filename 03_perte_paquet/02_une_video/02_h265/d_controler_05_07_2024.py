from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types, in_proto, ipv4, tcp, udp
from ryu import cfg

# Constants
QOS_METER_IDS = {
    "QOS1": 5000,
    "QOS2": 6000,
    "QOS3": 7000,
    "QOS4": 8000,
    "QOS5": 9000,
    "QOS6": 10000,
    "QOS7": 11000,
    "QOS8": 12000,
    "BE": 13000
}

class FlowManager:
    def __init__(self, datapaths):
        self.datapaths = datapaths

    def add_flow(self, datapath, priority, match, actions, buffer_id=None, idle=0, hard=0, meterid=0):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = []
        if meterid != 0:
            inst = [parser.OFPInstructionMeter(meterid),
                    parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        else:
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, buffer_id=buffer_id,
                                    idle_timeout=idle, hard_timeout=hard,
                                    priority=priority, match=match,
                                    instructions=inst)
        else:
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
        self.TOTAL_BW = 15000  # Define the total bandwidth capacity
        self.add_all_meters()

    def add_all_meters(self):
        for dpid in self.datapaths:
            self.add_meter(self.datapaths[dpid])

    def add_meter(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        total_bw = 0
        for qos, meter_id in QOS_METER_IDS.items():
            bw = getattr(self.CONF, f"{qos}_BANDWIDTH")
            total_bw += bw
            if total_bw > self.TOTAL_BW:
                self.logger.warning(f"Total QoS bandwidth {total_bw} kbps exceeds link capacity")
            mod = parser.OFPMeterMod(datapath, command=ofproto.OFPMC_ADD,
                                     flags=ofproto.OFPMF_KBPS, meter_id=meter_id,
                                     bands=[parser.OFPMeterBandDrop(rate=bw)])
            datapath.send_msg(mod)
            self.logger.info(f"Added meter {qos} with bandwidth {bw} kbps")

    def get_meter_id(self, protocol, src_port=0, dst_port=0):
        if protocol == in_proto.IPPROTO_TCP:  # TCP
            if src_port in range(5000, 13001) or dst_port in range(5000, 13001):
                return QOS_METER_IDS[f"QOS{(src_port // 1000) - 4}"] if src_port in range(5000, 13001) else QOS_METER_IDS[f"QOS{(dst_port // 1000) - 4}"]
            else:
                return QOS_METER_IDS["BE"]
        else:
            return QOS_METER_IDS["BE"]

    def get_stats(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        req = parser.OFPPortStatsRequest(datapath, 0, ofproto.OFPP_ANY)
        datapath.send_msg(req)

class Controller(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(Controller, self).__init__(*args, **kwargs)
        self.mac_to_port = {}
        self.datapaths = {}
        self.CONF = cfg.CONF
        self.CONF.register_opts([
            cfg.IntOpt('QOS_ENABLED', default=1, help='QOS Enabled'),
            cfg.StrOpt('ALGORITHM', default='STATIC', help='ALGORITHM'),
            cfg.IntOpt('QOS1_BANDWIDTH', default=1000, help='QOS1 Bandwidth in kbps'),
            cfg.IntOpt('QOS2_BANDWIDTH', default=1000, help='QOS2 Bandwidth in kbps'),
            cfg.IntOpt('QOS3_BANDWIDTH', default=1000, help='QOS3 Bandwidth in kbps'),
            cfg.IntOpt('QOS4_BANDWIDTH', default=1000, help='QOS4 Bandwidth in kbps'),
            cfg.IntOpt('QOS5_BANDWIDTH', default=1000, help='QOS5 Bandwidth in kbps'),
            cfg.IntOpt('QOS6_BANDWIDTH', default=1000, help='QOS6 Bandwidth in kbps'),
            cfg.IntOpt('QOS7_BANDWIDTH', default=1000, help='QOS7 Bandwidth in kbps'),
            cfg.IntOpt('QOS8_BANDWIDTH', default=1000, help='QOS8 Bandwidth in kbps'),
            cfg.IntOpt('BE_BANDWIDTH', default=1000, help='BE Bandwidth in kbps')
        ])
        self.logger.info(f"QOS_ENABLED: {self.CONF.QOS_ENABLED}")
        self.logger.info(f"ALGORITHM: {self.CONF.ALGORITHM}")
        for qos in range(1, 9):
            self.logger.info(f"QOS{qos}_BANDWIDTH: {getattr(self.CONF, f'QOS{qos}_BANDWIDTH')}")
        self.logger.info(f"BE_BANDWIDTH: {self.CONF.BE_BANDWIDTH}")
        self.qos = QoS(self.CONF, self.datapaths, self.logger)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        self.datapaths[datapath.id] = datapath
        self.qos.add_meter(datapath)

        # Add default flow to send all unmatched packets to the controller
        self.add_default_flow(datapath)

    def add_default_flow(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

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

        if out_port != ofproto.OFPP_FLOOD:
            if eth.ethertype == ether_types.ETH_TYPE_IP:
                ip = pkt.get_protocol(ipv4.ipv4)
                protocol = ip.proto
                match = None
                meter_id = 0

                if protocol == in_proto.IPPROTO_TCP:
                    t = pkt.get_protocol(tcp.tcp)
                    match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP,
                                            ipv4_src=ip.src, ipv4_dst=ip.dst, ip_proto=protocol,
                                            tcp_src=t.src_port, tcp_dst=t.dst_port)
                    meter_id = self.qos.get_meter_id(protocol, t.src_port, t.dst_port)

                elif protocol == in_proto.IPPROTO_UDP:
                    u = pkt.get_protocol(udp.udp)
                    match = parser.OFPMatch(eth_type=ether_types.ETH_TYPE_IP,
                                            ipv4_src=ip.src, ipv4_dst=ip.dst, ip_proto=protocol,
                                            udp_src=u.src_port, udp_dst=u.dst_port)
                    meter_id = self.qos.get_meter_id(protocol, u.src_port, u.dst_port)

                if match:
                    if self.CONF.QOS_ENABLED == 1:
                        self.qos.flow_manager.add_flow(datapath, 1, match, actions, idle=30, meterid=meter_id)
                    else:
                        self.qos.flow_manager.add_flow(datapath, 1, match, actions)

        data = None
        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=in_port, actions=actions, data=data)
        datapath.send_msg(out)

    def add_flow(self, datapath, priority, match, actions, buffer_id=None, idle=0, hard=0, meterid=0):
        self.qos.flow_manager.add_flow(datapath, priority, match, actions, buffer_id, idle, hard, meterid)

    def delete_flow(self, datapath, match):
        self.qos.flow_manager.delete_flow(datapath, match)

    def get_stats(self, datapath):
        self.qos.get_stats(datapath)

