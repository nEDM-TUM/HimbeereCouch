from setuptools import setup, find_packages

setup(
  name='himbeerecouch',
  version='0.0.11',
  packages=['himbeerecouch'],
  url='https://github.com/nEDM-TUM/HimbeereCouch',
  author='Michael Marino',
  author_email='mmarino@gmail.com',
  install_requires=['cloudant', 'netifaces']
)
