import datetime

from dateutil.tz import tzlocal


def test_datetime_without_timezone():
    from pseud.common import msgpack_packb, msgpack_unpackb

    date = datetime.datetime(2003, 9, 27, 9, 40, 1, 521290)
    assert msgpack_unpackb(msgpack_packb(date)) == date


def test_datetime_with_timezone():
    from pseud.common import msgpack_packb, msgpack_unpackb

    date = datetime.datetime(2003, 9, 27, 9, 40, 1, 521290,
                             tzinfo=tzlocal())
    assert msgpack_unpackb(msgpack_packb(date)) == date
