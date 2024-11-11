"""
Setup script for building the module into a package for publishing to PyPI.
"""

from setuptools import setup
import sys
import os

def get_version() -> str:
    """
    Get the package version from the environment variables.
    """

    major = os.environ.get('MAJOR', '1')
    minor = os.environ.get('MINOR', '0')
    patch = os.environ.get('PATCH', '0')

    return f'{major}.{minor}.{patch}'

def get_readme(filename: str = 'README.md') -> str:
    """
    Returns the contents of the requested README file
    """

    with open(filename, 'r') as file:
        return file.read()

def get_requirements(filename: str = 'requirements.txt') -> list:
    """
    Returns the contents of the requested requirements.txt
    file
    """

    with open(filename, 'r') as file:
        return [line.strip() for line in file if line.strip() and not line.startswith('#')]

def get_package_url(main_module: str) -> str:
    """
    Returns the URL for the package
    """

    repository_name = main_module.replace('_', '-')
    return f'https://github.com/thetestgame/{repository_name}'

def main() -> int:
    """
    Main entry point for the setup script
    """

    # Define some constants
    module_name = 'panda3d_astron'

    # Run the setup
    setup(
        name=module_name,
        description='',
        long_description=get_readme(),
        long_description_content_type='text/markdown',
        license='MIT',
        version=get_version(),
        author='Jordan Maxwell',
        maintainer='Jordan Maxwell',
        url=get_package_url(module_name),
        packages=[module_name],
        install_requires=[
            "panda3d",
            "panda3d-toolbox"
        ],
        classifiers=[
            'Programming Language :: Python :: 3',
        ])
    
    return 0

# Run the main function
if __name__ == '__main__':
    sys.exit(main())