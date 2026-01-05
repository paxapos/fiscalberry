import os
from setuptools import setup, find_packages

def load_requirements(filename):
    with open(filename, "r") as req_file:
        return [line.strip() for line in req_file
                if line.strip() and not line.startswith("#")]


setup(
    name='fiscalberry',
    version='2.0.0',
    description='Proyecto con interfaz Kivy y consola',
    author='Ale Vilar',
    author_email='alevilar@gmail.com',
    package_dir={'': 'src'},  # Le decimos que los paquetes están en "src"
    packages=find_packages(where='src'),  # Esto encontrará "fiscalberry"
    install_requires=load_requirements("requirements.txt"),  # Asume que load_requirements está fijo para tomar un nombre de archivo
    extras_require={
        'cli': load_requirements("requirements.cli.txt"),  # Assumes load_requirements is fixed to take a filename
        'gui': load_requirements("requirements.kivy.txt"),  # Assumes load_requirements is fixed to take a filename
    },
    entry_points={
        'console_scripts': [
            'fiscalberry_cli=fiscalberry.cli.main:main',
            'fiscalberry_gui=fiscalberry.desktop.main:main',
        ],
    },
)