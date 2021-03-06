#!/bin/bash

usage() {
    cat << EOF
    
    Usage: $0 <script> <title> <number of jobs> <files...>

    This script runs the input <script> against each file in <files...>
    on the SGE batch job system using -hold_jid to enforce a maximum
    number of jobs running at one time.

EOF
    exit 1
}

main() {
    nfs=$(echo $FILES | wc -w)
    nsplit=$(expr $nfs / $MAX + 1)
    
    SUBMITTED=()
    
    i=1
    group=1
    for f in $FILES; do
        if [ $i -gt $nsplit ]; then
            i=1
            let group+=1
        fi
        if [ $i -eq 1 ]; then
            HOLD=""
        else
            HOLD="-hold_jid ${SUBMITTED[$group]}"
        fi
    
        echo "Submitting: $group/$MAX: $i/$nsplit - $f"
    
        SUBMITTED[$group]=$(qsub -terse \
            -V -j y -l h_rt=48:00:00 -N ${TITLE}_${group}-${i} \
            $HOLD \
            $SCRIPT $f)
        let i+=1
    done
}

if [ -z $3 ]; then
    usage
fi

set -o errexit
set -o pipefail
set -o nounset

SCRIPT=$1
TITLE=$2
MAX=$3
FILES=${@:4}

main
