set -o errexit
set -o pipefail 
# See README for instructions on how to define this. You can comment this if
# you are ok with instal on your active python version
. set_environment.sh
set -o nounset 

# use this environment for debugging (comment line above)
# eval "$(${CONDA_DIR}/bin/conda shell.bash hook)"
# rm -Rf ./tmp_debug
# conda create -y -p ./tmp_debug
# conda activate ./tmp_debug

# fairseq
[ ! -d fairseq ] && git clone git@github.ibm.com:ramon-astudillo/fairseq.git
cd fairseq
git checkout modular_semantic_parsing
conda env update -f dcc/ccc_x86_fairseq.yml
# spacy needs to be installed with pip
pip install spacy
pip install --editable .
cd ..

# install pytorch scatter
rm -Rf  pytorch_scatter
git clone https://github.com/rusty1s/pytorch_scatter.git
cd pytorch_scatter
git checkout 1.3.2
# Ensure modern GCC
export GCC_DIR=/opt/share/gcc-5.4.0/x86_64/
export PATH=/opt/share/cuda-9.0/x86_64/bin:$GCC_DIR/bin:$PATH
export LD_LIBRARY_PATH=$GCC_DIR/lib:$LD_LIBRARY_PATH
export LD_LIBRARY_PATH=$GCC_DIR/lib64:$LD_LIBRARY_PATH
python setup.py develop
cd ..

# AMR tools
# without the dependencies (included in fairseq/dcc/ccc_pcc_fairseq.yml)
cp setup.py _setup.py.saved
sed '/install_requires=install_requires,/d' -i setup.py
pip install --editable . 
mv _setup.py.saved setup.py 

# smatch
[ ! -d smatch ] && git clone git@github.ibm.com:mnlp/smatch.git
cd smatch
git checkout f728c3d3f4a71b44678224d6934c1e67c4d37b89
cd ..
pip install smatch/

# for debugging
# conda install -y line_profiler
# pip install ipdb