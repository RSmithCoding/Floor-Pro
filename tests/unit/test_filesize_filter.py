import pytest

from floorpro.templating import filesize_filter, thousands_filter


@pytest.mark.parametrize(
    ("size", "text"),
    [
        (0, "0 bytes"),
        (980, "980 bytes"),
        (1023, "1,023 bytes"),
        (1024, "1 KB"),
        (12 * 1024 + 100, "12 KB"),
        (int(2.4 * 1024**2), "2.4 MB"),
        (int(1.1 * 1024**3), "1.1 GB"),
        (None, ""),
    ],
)
def test_filesize(size, text):
    assert filesize_filter(size) == text


def test_thousands():
    assert thousands_filter(1234) == "1,234"
    assert thousands_filter(None) == ""
