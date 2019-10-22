set -o nounset
set -o pipefail 
set -o errexit 

[ ! -d scripts/ ] && echo "Call as scripts/$(basename $0)" && exit 1
. scripts/local_variables.sh

# 'Yosuke shimazono wrote' appears mapped to write


# TRAIN
oracle_folder=data/austin0_copy_literal/
[ ! -d ${oracle_folder}/ ] && mkdir ${oracle_folder}/

# create oracle data
amr-oracle \
    --in-amr $train_file \
    --out-amr ${oracle_folder}/train.oracle.amr \
    --out-sentences ${oracle_folder}/train.tokens \
    --out-actions ${oracle_folder}/train.actions \
    --out-alignment-stats ${oracle_folder}/alignment.stats \
    --no-whitespace-in-actions


    #--in-propbank-args /dccstor/ramast1/_DATA/AMR/abstract_meaning_representation_amr_2.0/data/frames/propbank-frame-arg-descr.txt \

# parse a sentence step by step
amr-parse \
    --in-sentences ${oracle_folder}/train.tokens \
    --in-actions ${oracle_folder}/train.actions \
    --in-alignment-stats ${oracle_folder}/alignment.stats \
    --out-amr ${oracle_folder}/train.amr

exit

# evaluate oracle performance
# austin0: F-score: 0.9379
python smatch/smatch.py \
     --significant 4  \
     -f $train_file \
     ${oracle_folder}/train.oracle.amr \
     -r 10 

# DEV

# create oracle data
echo "Generating Oracle"
amr-oracle \
    --in-amr $dev_file \
    --out-amr ${oracle_folder}/dev.oracle.amr \
    --out-sentences ${oracle_folder}/dev.tokens \
    --out-actions ${oracle_folder}/dev.actions \

# parse a sentence step by step to explore
# amr-parse \
#     --in-sentences ${oracle_folder}/dev.tokens \
#     --in-actions ${oracle_folder}/dev.actions \
#     --out-amr ${oracle_folder}/dev.amr  # sanity check: should be the same as ${oracle_folder}/dev.oracle.amr

# evaluate oracle performance
echo "Evaluating Oracle"
# austin0: F-score: 0.9380
python smatch/smatch.py \
     --significant 4  \
     -f $dev_file \
     ${oracle_folder}/dev.oracle.amr \
     -r 10 
