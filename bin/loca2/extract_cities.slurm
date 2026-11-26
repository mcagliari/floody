#!/bin/bash
# LOCA2 city extraction on TACC Lonestar6, vm-small (floody/Plan.md Next steps 1e).
# Before the first chain: run the python command below once in `idev -p vm-small` with `--max-files 1` (the env
# must import and write on the job's node type; `vm-small` VMs lack CPU flags that login/compute nodes have).
# Identical restartable jobs; submit a chain so only one download runs at a time. From the job directory
# (`-o` below is relative to it and Slurm does not create it: `mkdir -p download-logs` first):
#   jid=$(sbatch --parsable extract_cities.slurm | grep -E '^[0-9]+' | tail -n1 | cut -d';' -f1); echo $jid
#   for i in 2 3 4 5 6; do jid=$(sbatch --parsable --dependency=afterany:$jid extract_cities.slurm | grep -E '^[0-9]+' | tail -n1 | cut -d';' -f1); echo $jid; done
# (TACC's sbatch prints the login banner to stdout: the filter keeps only the job id.)
# Resubmit while the last log line says files are left. Keep --time-limit (seconds) equal to -t.
#SBATCH -J loca2-cities
#SBATCH -p vm-small
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -t 02:00:00
#SBATCH -o download-logs/loca2-cities.%j.out
#SBATCH -A <ALLOCATION>
set -eo pipefail
unset PYTHONPATH                     # a module-set PYTHONPATH must not shadow the env

source $HOME/miniconda3/etc/profile.d/conda.sh     # adapt to your conda install
conda activate loca2

IN=$WORK/loca2_inputs                # filelist_ssp370.csv, city_boxes.json, ca-bundle.pem (copied from raw-loca2/)
# --work-dir on $WORK: downloads to $SCRATCH were much slower; one full file at a time, deleted after the cut
python $WORK/CausalFlow-flood-policies/floody/bin/loca2/extract_cities.py \
    --filelist $IN/filelist_ssp370.csv --boxes $IN/city_boxes.json --ca-bundle $IN/ca-bundle.pem \
    --work-dir $WORK/loca2_full --out-dir $WORK/loca2_cities --time-limit 7200
