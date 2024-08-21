#!/bin/bash

# (1) Reprendre le nom du répertoire courant où le script s'exécute
current_dir=$(pwd)

# (2) Lister les répertoires qui sont dans ce répertoire courant
dirs=($(ls -d */ 2>/dev/null | sed 's#/##'))

# (3) De cette liste, si "data_experiment" n'y est pas, créer ce répertoire
if [[ ! " ${dirs[@]} " =~ " data_experiment " ]]; then
    mkdir data_experiment
fi

# Recharger la liste des répertoires après la création éventuelle de "data_experiment"
dirs=($(ls -d */ 2>/dev/null | sed 's#/##'))

# (4) Rechercher les répertoires dont le nom commence par "end_exp_" et faire un "mov" vers "data_experiment"
for dir in "${dirs[@]}"; do
    if [[ $dir == end_exp_* ]]; then
        mv "$dir" "data_experiment/$dir"
    fi
done

# Afficher le message de fin
echo "Opération terminée : les répertoires et leur contenu ont été copiés vers 'data_experiment'."

