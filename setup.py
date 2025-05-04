import os
from setuptools import setup, find_packages

def load_requirements(filename):
    with open(filename, "r") as req_file:
        return [line.strip() for line in req_file
                if line.strip() and not line.startswith("#")]

requirements_file = os.path.join(os.path.dirname(__file__), "requirements.kivy.txt")
requirements = load_requirements(requirements_file)

setup(
    name='fiscalberry',
    version='2.0.0',
    description='Proyecto con interfaz Kivy y consola',
    author='Ale Vilar',
    author_email='alevilar@gmail.com',
    package_dir={'': 'src'},  # Le decimos que los paquetes están en "src"
    packages=find_packages(where='src'),  # Esto encontrará "fiscalberry"
    install_requires=requirements,
    entry_points={
        'console_scripts': [
            'fiscalberry_cli=fiscalberry.cli:main',
            'fiscalberry_gui=fiscalberry.gui:main',
        ],
    },
)