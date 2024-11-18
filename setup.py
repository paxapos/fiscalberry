from setuptools import setup

setup(
    name='fiscalberry',
    version='0.0.1',
    description='Proyecto con interfaz Kivy y consola',
    author='Ale Vilar',
    author_email='alevilar@gmail.com',
    packages=['fiscalberry'],
    install_requires=[
        'python-escpos==3.1',
        'python-socketio==5.11.3',
        'websocket-client==1.8.0',
        'simple-websocket==1.0.0',
        'requests==2.32.3',
        'aiohttp==3.10.11',
        'argparse==1.4.0',
        'uuid==1.30',
        'appdirs==1.4.4',
        'kivy==2.3.0',
        'platformdirs==4.2.2',
    ],
    entry_points={
        'console_scripts': [
        'mi_programa_consola=src.cli.cli:main',
        'mi_programa_kivy=src.kivy.main:main',
    ],
    },
)