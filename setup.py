from setuptools import setup


def read_that_file(path):
    with open(path) as open_file:
        return open_file.read()


long_description = '\n'.join((read_that_file('README.rst'),
                              read_that_file('LICENSE.txt')))

version = '1.0.1'


setup(name='pseud',
      version=version,
      description='Bidirectionnal RPC Api on top of pyzmq',
      long_description=long_description,
      author='Nicolas Delaby',
      author_email='ticosax@free.fr',
      url='https://github.com/ticosax/pseud',
      license='Apache Software License',
      packages=['pseud'],
      include_package_data=True,
      zip_safe=True,
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
