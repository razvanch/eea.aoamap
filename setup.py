""" Installer
"""
from setuptools import setup, find_packages
import os
from os.path import join

NAME = 'eea.aoamap'
PATH = NAME.split('.') + ['version.txt']
VERSION = open(join(*PATH)).read().strip()

setup(
    name=NAME,
    version=VERSION,
    description="",
    long_description=open("README.rst").read() + "\n" +
                     open(os.path.join("docs", "HISTORY.txt")).read(),
    author='Eau de Web',
    author_email='office@eaudeweb.ro',
    url='http://www.eea.europa.eu/data-and-maps',
    packages=find_packages(),
    include_package_data=True,
    zip_safe=False,
    install_requires=[
      'lxml',
      'BeautifulSoup',
    ]
)
