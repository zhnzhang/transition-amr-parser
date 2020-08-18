Transition-based AMR Parser
============================

Pytorch implementation of a transition-based parser for Abstract Meaning Representation (AMR). The code includes oracle and state-machine for AMR and an implementation of a stack-LSTM following [(Ballesteros and Al-Onaizan 2017)](https://arxiv.org/abs/1707.07755v1) with some improvements from [(Naseem et al 2019)](https://arxiv.org/abs/1905.13370). Initial commit developed by Miguel Ballesteros and Austin Blodgett while at IBM.

## Using the Parser

- to use the existing GRPC service check [services](https://github.ibm.com/mnlp/transition-amr-parser/wiki/Parsing-Services)
- to install through the Watson-NLP artifactory, see the [wiki](https://github.ibm.com/mnlp/transition-amr-parser/wiki/Installing-the-python-package-through-Artifactory)
- to install the parser manually, see [Manual Install](#manual-install)

Before using the parser, please refer the [Tokenizer](#tokenizer) section on what tokenizer to use.

To use from the command line with a trained model do

```bash
amr-parse \
  --in-tokenized-sentences $input_file \
  --in-checkpoint $in_checkpoint \
  --out-amr file.amr
```

Here `$input_file` contains one sentence per line (or various in multi-sentence
settings). `$in_checkpoint` is the pytorch checkpoint of a trained model.
`file.amr` will contain the PENNMAN notation AMR with additional alignment
information as comments.

To use from other Python code with a trained model do

```python
from transition_amr_parser.stack_transformer_amr_parser import AMRParser
parser = AMRParser.from_checkpoint(in_checkpoint) 
annotations = parser.parse_sentences([['The', 'boy', 'travels'], ['He', 'visits', 'places']])
print(annotations.toJAMRString())
```

## Manual Install

The code has been tested on Python `3.6` to install

```bash
git clone git@github.ibm.com:mnlp/transition-amr-parser.git
cd transition-amr-parser
# here optionally activate your virtual environment
pip install --editable .
```

This will pip install the repo in `--editable` mode. You will also need to
download smatch toos if you want to run evaluations

```bash
git clone git@github.ibm.com:mnlp/smatch.git
pip install smatch/
```

The spacy tools will be updated on first use. To do this manually do

```bash
python -m spacy download en
```

## Manual Install on CCC

Clone this repository and check out the appropriate branch:

    git clone git@github.ibm.com:mnlp/transition-amr-parser.git
    cd transition-amr-parser
    git checkout v0.3.0rc

There are also install scripts for the CCC with an environment setter. Copy it
from here 

    cp /dccstor/ykt-parse/SHARED/MODELS/AMR/transition-amr-parser/set_environment.sh .
    chmod u+w set_environment.sh

Edit the `set_environment.sh` file to replace the string `"$(/path/to/miniconda3/bin/conda shell.bash hook)"` 
with the path to your own `conda` installation. If you don't know the path to your `conda` 
installation, try looking at the `CONDA_EXE` environment variable:

    echo $CONDA_EXE

For instructions on how to install PPC conda see
[here](https://github.ibm.com/ramon-astudillo/C3-tools#conda-pytorch-installation-for-the-power-pcs).

Then to install in `x86` machines, from a `x86` computing node do 

    bash scripts/install_x86_with_conda.sh

For PowerPC from a `ppc` computing node do

    bash scripts/install_ppc_with_conda.sh

to check if the install worked in either `x86` or `ppc` machines,
log in to a compute node with a GPU and run the `correctly_installed.py` program:

    . set_environment.sh
    python tests/correctly_installed.py

## Decode with Pre-trained model

To do decoding tests you will need to copy a model. You can soft-link the
features

```bash
mkdir -p DATA/AMR/oracles/
ln -s /dccstor/ykt-parse/SHARED/MODELS/AMR/transition-amr-parser/oracles/o3+Word100 DATA/AMR/oracles/
mkdir -p DATA/AMR/features/
ln -s /dccstor/ykt-parse/SHARED/MODELS/AMR/transition-amr-parser/features/o3+Word100_RoBERTa-base DATA/AMR/features/
mkdir -p DATA/AMR/models/
cp -R /dccstor/ykt-parse/SHARED/MODELS/AMR/transition-amr-parser/models/o3+Word100_RoBERTa-base_stnp6x6-seed42 DATA/AMR/models/
chmod u+w DATA/AMR/models/o3+Word100_RoBERTa-base_stnp6x6-seed42/beam1
```

To do a simple test run for decoding, on a computing node with a GPU, do

```bash
bash scripts/stack-transformer/test.sh DATA/AMR/models/o3+Word100_RoBERTa-base_stnp6x6-seed42/config.sh DATA/AMR/models/o3+Word100_RoBERTa-base_stnp6x6-seed42/checkpoint70.pt
```

the results will be stored in
`DATA/AMR/models/o3+Word100_RoBERTa-base_stnp6x6-seed42/beam1`. Copy the config
and modify for further experiments.

## Training your Model

This assumes that you have access to the usual AMR training set from LDC
(LDC2017T10). You will need to apply preprocessing to build JAMR and Kevin
Alignments using the same tokenization and then merge them together. You must
have the following installed: pip, g++, and ICU
(http://site.icu-project.org/home).
```bash
cd preprocess
bash preprocess.sh path/to/ldc_data_home
```
New files will be `train.aligned.txt`, `test.aligned.txt` and `dev.aligned.txt` . The process will take ~1 hour to run for AMR 2.0. 

Then call the train script with appropriately set paths

```
bash scripts/train.sh 
```

You must define `set_environment.sh` containing following environment variables

```bash
# amr files
train_file 
dev_file 
# berts in hdf5 (see sample data)
train_bert  
dev_bert 
# experiment data
name 
# hyperparameters
num_cores=10
batch_size=10 
lr=0.005 
```

## Test Run on sample data

We provide annotated examples in `data/` with CC-SA 4.0 license. We also
provide a sample of the corresponding BERT embeddings. This can be used as a
sanity check (but data amount insufficient for training) . To test training
```
amr-learn -A data/wiki25.jkaln -a data/wiki25.jkaln -B data/wiki25.bert_max_cased.hdf5 -b data/wiki25.bert_max_cased.hdf5 --name toy-model
```

# More information

## Action set

The transition-based parser operates using 10 actions:

  - `SHIFT` : move buffer0 to stack0
  - `REDUCE` : delete token from stack0
  - `CONFIRM` : assign a node concept
  - `SWAP` : move stack1 to buffer
  - `LA(label)` : stack0 parent of stack1
  - `RA(label)` : stack1 parent of stack0
  - `ENTITY(type)` : form a named entity
  - `MERGE` : merge two tokens (for MWEs)
  - `DEPENDENT(edge,node)` : Add a node which is a dependent of stack0
  - `CLOSE` : complete AMR, run post-processing

There are also two optional actions using SpaCy lemmatizer `COPY_LEMMA` and
`COPY_SENSE01`. These actions copy `<lemma>` or `<lemma>-01` to form a node
name.
  
## Files

amr.py : contains a basic AMR class and a class JAMR_CorpusReader for reading AMRs from JAMR format.
  
state_machine.py : Implement AMR state machine with a stack and buffer 

data_oracle.py : Implements oracle to assign gold actions.

learn.py : Runs the parser (use `learn.py --help` for options)

stack_lstm.py : Implements Stack-LSTM. 

entity_rules.json : Stores rules applied by the ENTITY action 

## Tokenizer

For best performance, it is recommended to use the same tokenizer while testing and training. The model works best with the JAMR Tokenizer. 

When using the `AMRParser.parse_sentence` method, the parser expects the input to be tokenized words.

When using the parser as a command line interface, the input file must contain 1 sentence per line. Also, generate these sentences by first tokenizing the raw sentences using a tokenizer of your choice and then joining the tokens using white space (Since the model just uses white space tokenization when called via CLI).
