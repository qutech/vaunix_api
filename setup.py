from setuptools import setup, find_packages

import re
import os


def extract_version(version_file):
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              version_file, re.M)
    if version_match:
        return version_match.group(1)
    raise RuntimeError("Unable to find version string.")


def readme():
    with open("README.md", "r") as fh:
        return fh.read()


def init_file_content():
    with open(os.path.join('vaunix_api', '__init__.py'), 'r') as init_file:
        return init_file.read()


setup(name='vaunix_api',
      version=extract_version(init_file_content()),
      use_2to3=False,
      maintainer='Simon Humpohl',
      maintainer_email='simon.humpohl@rwth-aachen.de',
      description='Wrapper around VNX API to control signal generators, attenuators etc by vaunix',
      long_description=readme(),
      url='https://github.com/qutech/vaunix_api',
      classifiers=[
          'Development Status :: 3 - Alpha',
          'Intended Audience :: Science/Research',
          'Programming Language :: Python :: 3 :: Only',
          'Programming Language :: Python :: 3.5',
          'Topic :: Scientific/Engineering'
      ],
      license='GPL',
      packages=find_packages(),
      install_requires=[],
      keywords=['vaunix', 'labbrick'],

      # Package can download dll by vaunix and needs a directory for that
      zip_safe=False)
