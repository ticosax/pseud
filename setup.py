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

long_description = '\n'.join((read_that_file('README.rst'),
                              read_that_file('LICENSE.txt')))

version = '0.0.4'


setup(name='pseud',
      version=version,
      description='Bidirectionnal RPC Api on top of pyzmq',
      author='Nicolas Delaby',
      author_email='nicolas.delaby@ezeep.com',
      url='https://github.com/ezeep/pseud',
      license='Apache Software License',
      packages=['pseud'],
      include_package_data=True,
      zip_safe=True,
      install_requires=[
          'pyzmq',
          'msgpack-python',
          'zope.component',
          'python-dateutil',
      ],
      extras_require={'Tornado': ('tornado', 'futures'),
                      'Gevent': ('gevent',),
                      'doc': ('sphinx', 'repoze.sphinx.autointerface')},
      tests_require=[
          'pytest',
          'pytest-cov',
          'coveralls',
      ],
      cmdclass={'test': PyTest},
      classifiers=[
          'Development Status :: 4 - Beta',
          'Intended Audience :: Developers',
          'Intended Audience :: System Administrators',
          'License :: OSI Approved :: Apache Software License',
          'Operating System :: OS Independent',
          'Programming Language :: Python :: 2.7',
      ]
      )
