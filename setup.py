from setuptools import setup, find_packages

setup(
  name='himbeerecouch',
  version='0.0.13',
  packages=['himbeerecouch'],
  url='https://github.com/nEDM-TUM/HimbeereCouch',
  author='Michael Marino',
  author_email='mmarino@gmail.com',
  install_requires=['pynedm>=0.1.0', 'netifaces'],
  dependency_links=[
    "https://github.com/nEDM-TUM/Python-Slow-Control/tarball/master#egg=pynedm-0.1.0"
  ]
)
