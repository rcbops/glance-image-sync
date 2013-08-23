import os
from setuptools import setup

# Utility function to read the README file.
# Used for the long_description.  It's nice, because now 1) we have a top level
# README file and 2) it's easier to type in the README file than to put a raw
# string in below ...
def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name = "rcb",
    version = "0.1.0",
    author = "Matt Thompson",
    author_email = "mattt@defunct.ca",
    description = ("RCB OpenStack python tools"),
    license = "BSD",
    keywords = "example documentation tutorial",
    url = "http://github.com/rcbops/glance-image-sync",
    packages=['rcb',],
    long_description=read('README.md'),
    #classifiers=[
    #    "Development Status :: 3 - Alpha",
    #    "Topic :: Utilities",
    #    "License :: OSI Approved :: BSD License",
    #],
    entry_points={'console_scripts':
                  ['glance-image-sync=rcb.glance_image_sync:main']}
)
