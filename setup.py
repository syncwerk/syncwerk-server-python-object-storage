from setuptools import setup, find_packages
setup(
    name='syncwerk-server-python-object-storage',
    version='20181227',
    author='Syncwerk GmbH',
    author_email='support@syncwerk.com',
    packages=find_packages(),
    url='https://www.syncwerk.com',
    license='Apache 2.0',
    description='Object Storage bindings',
    long_description='A Python module for accessing the Syncwerk object storage',
    platforms=['any'],
    include_package_data=True,
)
