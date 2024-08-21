

ubuntu  22.04, avec OVS 1.13 minimum


Steps
======

1. Configure QoS value in params.conf


2. Run the RYU Controller application

ryu-manager  --config-file params.conf controleur.py

ryu-manager controleur.py



3. Run the Mininet topology


sudo python3 classe_1_experimentation.py

