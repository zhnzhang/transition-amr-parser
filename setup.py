import os
import subprocess
from setuptools import setup, find_packages

VERSION = '0.4.0'

package_data = {
    'transition_amr_parser': [
        'config.json',
        'entity_rules.json',
        'train.rules.json'
     ]
}

# this is what usually goes on requirements.txt
install_requires = [
    'torch',
    'h5py',
    'spacy==2.2.3',
    'tqdm',
    'fairseq'
]

# You need to pip install the requirements.txt first
setup(
    name='transition_amr_parser',
    version=VERSION,
    description="Trasition-based AMR parser tools",
    py_modules=['transition_amr_parser'],
    entry_points={
        'console_scripts': [
            'amr-learn = transition_amr_parser.learn:main',
            'amr-parse = transition_amr_parser.parse:main',
            'amr-oracle = transition_amr_parser.data_oracle:main',
            'amr-fake-parse = transition_amr_parser.fake_parse:main',
            'amr-edit = transition_amr_parser.edit:main'
        ]
    },
    packages=find_packages()
)
