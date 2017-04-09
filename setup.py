from setuptools import setup


def read_that_file(path):
    with open(path) as open_file:
        return open_file.read()


long_description = '\n'.join((read_that_file('README.rst'),
                              read_that_file('LICENSE.txt')))

version = '1.0.0-a1'


setup(name='pseud',
      version=version,
      description='Bidirectionnal RPC Api on top of pyzmq',
      author='Nicolas Delaby',
      author_email='ticosax@free.fr',
      url='https://github.com/ticosax/pseud',
      license='Apache Software License',
      packages=['pseud'],
      include_package_data=True,
      zip_safe=True,
      install_requires=[
          'pyzmq>=14.4',
          'msgpack-python',
          'zope.component',
      ],
      extras_require={'doc': ('sphinx', 'repoze.sphinx.autointerface')},
      tests_require=[
          'pytest',
          'pytest-cov',
          'pytest-pep8',
          'pytest-capturelog',
          'pytest-asyncio',
          'tox',
      ],
      classifiers=[
          'Development Status :: 4 - Beta',
          'Intended Audience :: Developers',
          'Intended Audience :: System Administrators',
          'License :: OSI Approved :: Apache Software License',
          'Operating System :: OS Independent',
          'Programming Language :: Python :: 3.6',
      ],
      keywords='rpc zeromq pyzmq curve bidirectional asyncio',
      )
