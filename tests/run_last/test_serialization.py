import datetime

from dateutil.tz import tzlocal


def test_datetime_without_timezone():
    from pseud.packer import Packer

    date = datetime.datetime(2003, 9, 27, 9, 40, 1, 521290)
    assert Packer().unpackb(Packer().packb(date)) == date


def test_datetime_with_timezone():
    from pseud.packer import Packer

    date = datetime.datetime(2003, 9, 27, 9, 40, 1, 521290,
                             tzinfo=tzlocal())
    assert Packer().unpackb(Packer().packb(date)) == date
