"""Packer encapsulation from aiozmq.rpc.packer.

Slightly modified to support python 2.7 and match pseud style more.

Copyright (c) 2013, 2014, Nikolay Kim and Andrew Svetlov
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are
met:

1. Redistributions of source code must retain the above copyright
notice, this list of conditions and the following disclaimer.

2. Redistributions in binary form must reproduce the above copyright
notice, this list of conditions and the following disclaimer in the
documentation and/or other materials provided with the distribution.

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
"AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
"""

import datetime
import functools
import itertools
import logging
import pickle

import msgpack

logger = logging.getLogger(__name__)

_pickle_dumps = functools.partial(
    pickle.dumps, protocol=pickle.HIGHEST_PROTOCOL)
_datetime_objs = (
    datetime.tzinfo, datetime.timedelta, datetime.datetime, datetime.date)
_default = {
    i: (cls, _pickle_dumps, pickle.loads)
    for i, cls in enumerate(_datetime_objs, start=123)
}


class Packer:

    def __init__(self, translation_table=None):
        if translation_table is None:
            translation_table = _default
        else:
            translation_table = dict(
                itertools.chain(_default.items(), translation_table.items()))
        self.translation_table = translation_table
        self._pack_cache = {}

    def packb(self, data):
        try:
            return msgpack.packb(data, encoding='utf-8', use_bin_type=True,
                                 default=self.ext_type_pack_hook)
        except Exception:
            logger.exception('Packing failed')
            raise

    def unpackb(self, packed):
        try:
            return msgpack.unpackb(packed, use_list=False, encoding='utf-8',
                                   ext_hook=self.ext_type_unpack_hook)
        except Exception:
            logger.exception('Unpacking failed')
            raise

    def ext_type_pack_hook(self, obj, _sentinel=object()):
        obj_class = obj.__class__
        hit = self._pack_cache.get(obj_class, _sentinel)
        if hit is None:
            # packer has been not found by previous long-lookup
            raise TypeError("Unknown type: {!r}".format(obj))
        elif hit is _sentinel:
            # do long-lookup
            for code in sorted(self.translation_table):
                cls, packer, unpacker = self.translation_table[code]
                if isinstance(obj, cls):
                    self._pack_cache[obj_class] = (code, packer)
                    return msgpack.ExtType(code, packer(obj))
            else:
                self._pack_cache[obj_class] = None
                raise TypeError("Unknown type: {!r}".format(obj))
        else:
            # do shortcut
            code, packer = hit
            return msgpack.ExtType(code, packer(obj))

    def ext_type_unpack_hook(self, code, data):
        try:
            cls, packer, unpacker = self.translation_table[code]
            return unpacker(data)
        except KeyError:
            return msgpack.ExtType(code, data)

    def register_ext_handler(self, code, base_class, packer, unpacker):
        if code in self.translation_table:
            raise ValueError('Code %s is already in the table: %s' % (
                code, self.translation_table))
        self.translation_table[code] = (base_class, packer, unpacker)
        self._pack_cache.pop(base_class, None)
