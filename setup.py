import sys

from setuptools import setup
from setuptools.command.test import test as TestCommand


class PyTest(TestCommand):

    def finalize_options(self):
        TestCommand.finalize_options(self)
        self.test_args = []
        self.test_suite = True

    def run_tests(self):
        import pytest
        errno = pytest.main(self.test_args)
        sys.exit(errno)


version = '0.0.1dev'


setup(name='pybidirpc',
      version=version,
      description='Bidirectionnal RPC Api on top of pzmq',
      author='Nicolas Delaby',
      author_email='nicolas.delaby@ezeep.com',
      url='',
      package_dir={'': 'src'},
      packages=['pybidirpc'],
      zip_safe=True,
      install_requires=[
          'pyzmq',
          'msgpack-python',
          'tornado',
          'futures',
          'zope.component'
      ],
      tests_require=[
          'pytest',
      ],
      cmdclass={'test': PyTest},
      )
