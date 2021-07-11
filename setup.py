#!/usr/bin/env python

from pathlib import Path
from setuptools import setup

version="0.1.0"

setup(
    name="pkg-testing-tools",
    version=version,
    description="Packages testing tools for Gentoo",
    long_description=Path('README.md').read_text(),
    long_description_content_type='text/markdown',
    author="Piotr Karbowski",
    license="BSD",
    url="https://github.com/slashbeast/pkg-testing-tools",
    download_url = "https://github.com/slashbeast/pkg-testing-tools/archive/v{}.tar.gz".format(version),
    install_requires=[],
    package_dir={'pkg_testing_tool': 'src/pkg_testing_tool'},
    packages=['pkg_testing_tool'],
    entry_points={'console_scripts': ['pkg-testing-tool = pkg_testing_tool:main']},
)
