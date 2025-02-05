set -o errexit
set -o pipefail
. set_environment.sh
[ -z $1 ] && echo "$0 <amr_file (no wiki)>" && exit 1
gold_amr=$1
set -o nounset 

oracle_folder=DATA/AMR2.0/oracles/o10_pinitos/
mkdir -p $oracle_folder 

# get actions from oracle
python transition_amr_parser/amr_machine.py \
    --in-aligned-amr $gold_amr \
    --out-machine-config $oracle_folder/machine_config.json \
    --out-actions $oracle_folder/train.actions \
    --out-tokens $oracle_folder/train.tokens \
    --use-copy 1 \
    --absolute-stack-positions  \
    # --reduce-nodes all

# play actions on state machine
python transition_amr_parser/amr_machine.py \
    --in-machine-config $oracle_folder/machine_config.json \
    --in-tokens $oracle_folder/train.tokens \
    --in-actions $oracle_folder/train.actions \
    --out-amr $oracle_folder/train_oracle.amr

# score
echo "Conmputing Smatch (make take long for 1K or more sentences)"
smatch.py -r 10 --significant 4 -f $gold_amr $oracle_folder/train_oracle.amr
