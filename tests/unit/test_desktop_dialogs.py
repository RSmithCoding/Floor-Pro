"""NativeDialogs, driven by a stub webview module and window (no GUI needed)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from floorpro.desktop import NativeDialogs

STUB_WEBVIEW = SimpleNamespace(
    FileDialog=SimpleNamespace(SAVE="SAVE", FOLDER="FOLDER", OPEN="OPEN")
)


class StubWindow:
    def __init__(self, result):
        self.result = result
        self.calls: list[tuple] = []

    def create_file_dialog(self, dialog_type, **kwargs):
        self.calls.append((dialog_type, kwargs))
        return self.result


def dialogs(result):
    window = StubWindow(result)
    return NativeDialogs(STUB_WEBVIEW, window), window


@pytest.mark.parametrize("result", ["/tmp/a.fpbackup", ("/tmp/a.fpbackup",), ["/tmp/a.fpbackup"]])
def test_save_path_returns_a_path(result):
    native, window = dialogs(result)
    assert native.save_path("a.fpbackup") == Path("/tmp/a.fpbackup")
    dialog_type, kwargs = window.calls[0]
    assert dialog_type == "SAVE"
    assert kwargs["save_filename"] == "a.fpbackup"
    assert Path(kwargs["directory"]).is_dir()


@pytest.mark.parametrize("result", [None, (), ""])
def test_cancelled_dialogs_return_none(result):
    native, _ = dialogs(result)
    assert native.save_path("x") is None
    assert native.choose_folder() is None
    assert native.open_file() is None


def test_choose_folder():
    native, window = dialogs(("/Volumes/USB",))
    assert native.choose_folder() == Path("/Volumes/USB")
    assert window.calls[0][0] == "FOLDER"


def test_open_file_filters_backups():
    native, window = dialogs(("/tmp/b.fpbackup",))
    assert native.open_file() == Path("/tmp/b.fpbackup")
    dialog_type, kwargs = window.calls[0]
    assert dialog_type == "OPEN"
    assert kwargs["file_types"] == ("FloorPro backups (*.fpbackup)", "All files (*.*)")
    assert kwargs["allow_multiple"] is False
