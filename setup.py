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


def read_that_file(path):
    with open(path) as open_file:
        return open_file.read()

long_description = '\n'.join((read_that_file('README.rst'),))

version = '0.0.1dev'


setup(name='pseud',
      version=version,
      description='Bidirectionnal RPC Api on top of pzmq',
      author='Nicolas Delaby',
      author_email='nicolas.delaby@ezeep.com',
      url='',
      packages=['pseud'],
      include_package_data=True,
      zip_safe=True,
      install_requires=[
          'pyzmq',
          'msgpack-python',
          'zope.component'
      ],
      extras_require={'Tornado': ('tornado', 'futures'),
                      'Gevent': ('gevent',)},
      tests_require=[
          'pytest',
      ],
      cmdclass={'test': PyTest},
      )
