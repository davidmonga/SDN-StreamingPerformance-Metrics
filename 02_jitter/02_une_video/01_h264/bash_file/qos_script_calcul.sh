#!/bin/bash

# Définir les arguments passés au script bash
FILE_PATH="$1"
IP_SRC="$2"
IP_DST="$3"

# Utiliser tshark pour extraire les timestamps et la taille des paquets
tshark -r "$FILE_PATH" -Y "(ip.src == $IP_SRC && ip.dst == $IP_DST && tcp) || (ip.src == $IP_DST && ip.dst == $IP_SRC && tcp)" -T fields -e frame.time_epoch -e frame.len | \
awk '
BEGIN {
    prev_timestamp = 0;
    total_latency = 0;
    jitter_sum = 0;
    jitter_count = 0;
    diff_squares_sum = 0;
    count = 0;
    total_data = 0;
    start_time = 0;
    end_time = 0;
    lost_packets = 0;
}
{
    if (NR % 2 == 0) {
        latency_diff = $1 - prev_timestamp;
        total_latency += latency_diff;
        
        if (start_time == 0) {
            start_time = $1;
        }
        end_time = $1;
        
        if (prev_jitter_timestamp != 0) {
            jitter = $1 - prev_jitter_timestamp;
            abs_jitter = jitter < 0 ? -jitter : jitter;
            jitter_sum += abs_jitter;
            diff_squares_sum += abs_jitter * abs_jitter;
            jitter_count++;
        }
        prev_jitter_timestamp = $1;
    }
    
    prev_timestamp = $1;
    total_data += $2;
    count++;
}
END {
    if (count > 0) {
        total_time = end_time - start_time;
        average_latency = total_latency / (count / 2);
        average_jitter = jitter_sum / jitter_count;
        mean_diff = diff_squares_sum / jitter_count;
        std_dev_jitter = sqrt(mean_diff);
        bitrate = (total_data * 8) / (total_time * 1000000); # Convertir le temps en secondes et les données en mégabits
        packet_loss_percentage = (lost_packets / count) * 100;
        # Formater la sortie pour faciliter la récupération depuis Python
        print "bitrate:", bitrate, "packet_loss:", packet_loss_percentage, "average_latency:", average_latency, "average_jitter:", average_jitter;
    }
}'

