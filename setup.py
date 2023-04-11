# coding: utf-8

import os
from setuptools import setup

# Import readme
with open(os.path.join(os.path.dirname(__file__), 'README.md')) as readme_file:
    readme = readme_file.read()

# Setup
setup(
    name='cloud-cost-allocation',
    version='1.0.3',
    description='Python library for shared, hierarchical cost allocation based on user-defined usage metrics.',
    long_description=readme,
    long_description_content_type='text/markdown',
    packages=['cloud_cost_allocation',
              'cloud_cost_allocation.reader',
              'cloud_cost_allocation.utils',
              'cloud_cost_allocation.writer'],
    license='MIT license',
    url="https://github.com/AmadeusITGroup/cloud-cost-allocation",
    maintainer='Amadeus IT Group',
    maintainer_email='opensource@amadeus.com',
    classifiers=[
        "Development Status :: 2 - Pre-Alpha",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        "Programming Language :: Python :: 3.10",
        "Topic :: Office/Business :: Financial"
    ],
)
