try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

long_description = open('README.md').read()

setup(
    name='panda3d_astron',
    description='Panda3D Astron server support as a Python 3 module. Allows the use of Astron with stock Panda3D',
    long_description=long_description,
    license='MIT',
    version='1.0.0',
    author='Jordan Maxwell',
    maintainer='Jordan Maxwell',
    url='https://github.com/thetestgame/panda3d_astron',
    packages=['panda3d_astron'],
    install_requires=['panda3d'],
    classifiers=[
        'Programming Language :: Python :: 3',
    ])