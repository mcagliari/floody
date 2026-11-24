#!/bin/bash
# LOCA2 city extraction on TACC Lonestar6, vm-small (floody/Plan.md Next steps 1e).
# Identical restartable jobs; submit a chain so only one download runs at a time:
#   jid=$(sbatch --parsable extract_cities.slurm)
#   for i in 2 3 4 5 6; do jid=$(sbatch --parsable --dependency=afterany:$jid extract_cities.slurm); done
# Resubmit while the last log line says files are left. Keep --time-limit equal to -t below (seconds).
#SBATCH -J loca2-cities
#SBATCH -p vm-small
#SBATCH -N 1
#SBATCH -n 1
#SBATCH -t 02:00:00
#SBATCH -o loca2-cities.%j.out
#SBATCH -A <ALLOCATION>
set -eo pipefail

source <PATH TO>/conda.sh          # e.g. the miniforge install under $WORK
conda activate loca2

IN=$WORK/loca2_inputs              # filelist_ssp370.csv, city_boxes.json, ca-bundle.pem (copied from raw-loca2/)
python <PATH TO>/floody/bin/loca2/extract_cities.py \
    --filelist $IN/filelist_ssp370.csv --boxes $IN/city_boxes.json --ca-bundle $IN/ca-bundle.pem \
    --work-dir $SCRATCH/loca2_full --out-dir $WORK/loca2_cities --time-limit 7200
