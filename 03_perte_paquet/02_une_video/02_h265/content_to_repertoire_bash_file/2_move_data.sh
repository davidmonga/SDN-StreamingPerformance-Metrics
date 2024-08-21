#!/bin/bash

# Fonction pour afficher l'utilisation du script
usage() {
    echo "Usage: $0 data_experiment repertoire_data servers clients perturbation_numbers_deplacement protocole codec perturbation nombre_hotes"
    exit 1
}

# Vérifier le nombre d'arguments
if [ "$#" -ne 9 ]; then
    usage
fi

# Récupération des arguments
data_experiment=$1
repertoire_data=$2
servers=$3
clients=$4
perturbation_numbers_deplacement=$5
protocole=$6
codec=$7
perturbation=$8
nombre_hotes=$9

# Convertir les chaînes en tableaux
IFS=',' read -r -a server_array <<< "$servers"
IFS=',' read -r -a client_array <<< "$clients"
IFS=',' read -r -a perturbation_numbers <<< "$perturbation_numbers_deplacement"

# Création du tableau des paires serveur-client
server_client_tab=()
for index in "${!server_array[@]}"; do
    server=${server_array[$index]}
    client=${client_array[$index]}
    server_client_tab+=("${server}_${client}")
done

# Fichiers temporaires
temp_directories=$(mktemp)
temp_files=$(mktemp)

# Fonction pour déplacer les fichiers pour une paire serveur-client
move_files_for_pair() {
    local server_client=$1
    shift
    local perturbation_numbers=("$@")

    IFS='_' read -r server client <<< "$server_client"

    for perturbation_number in "${perturbation_numbers[@]}"; do
        start_time=$(date +%s)
        
        source_dir="$PWD/$data_experiment/end_exp_${perturbation}_${perturbation_number}/chunks-${server}_${client}_bbb_${codec}_${protocole}_hotes_${nombre_hotes}_${perturbation}_${perturbation_number}"
        
        if [ ! -d "$source_dir" ]; then
            continue
        fi

        target_dir="$PWD/$repertoire_data/${server}_${client}/$perturbation_number/$(basename "$source_dir")"
        mkdir -p "$target_dir"
        cp -r "$source_dir/"* "$target_dir"

        source_file="$PWD/$data_experiment/end_exp_${perturbation}_${perturbation_number}/${server}_${client}_bbb_${codec}_${protocole}_hotes_${nombre_hotes}_${perturbation}_${perturbation_number}.pcapng"
        
        if [ -f "$source_file" ]; then
            cp "$source_file" "$(dirname "$target_dir")"
        fi

        end_time=$(date +%s)
        elapsed_time=$((end_time - start_time))
        
        echo "Couple: ${server}_${client}, Perturbation: $perturbation_number, Temps: ${elapsed_time}s"

        echo "${server}_${client},$perturbation_number,$target_dir" >> "$temp_directories"

        if [ -f "$source_file" ]; then
            echo "${server}_${client},$perturbation_number,$source_file" >> "$temp_files"
        fi
    done
}

# Création du répertoire de destination s'il n'existe pas
current_directory=$PWD
repertoire_data_path="$current_directory/$repertoire_data"
mkdir -p "$repertoire_data_path"

# Exportation des variables et de la fonction
export -f move_files_for_pair
export temp_directories temp_files
export data_experiment repertoire_data codec protocole nombre_hotes perturbation

# Préparation des arguments pour xargs
args_list=()
for server_client in "${server_client_tab[@]}"; do
    for perturbation_number in "${perturbation_numbers[@]}"; do
        args_list+=("$server_client $perturbation_number")
    done
done

# Déplacement des fichiers pour chaque paire serveur-client en parallèle avec xargs
printf "%s\n" "${args_list[@]}" | xargs -P 7 -I {} bash -c 'move_files_for_pair {}'

# Écriture des fichiers temporaires dans les fichiers finaux
cat "$temp_directories" > directories.txt
cat "$temp_files" > files.txt

# Suppression des fichiers temporaires
rm "$temp_directories" "$temp_files"

