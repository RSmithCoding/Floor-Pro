"""Logs never contain passwords, keys or customer details (constitution: logging)."""

from __future__ import annotations

import base64
import json
import logging

from floorpro.services import backup_service
from tests.conftest import make_customer

SECRET = "my very secret backup pw"
NEW_SECRET = "an even more secret pw"


def use_this_tests_log_file():
    """The file handler is configured once per process; point it at this test's data folder."""
    from floorpro.logging_setup import configure_logging

    root = logging.getLogger()
    for handler in list(root.handlers):
        if getattr(handler, "name", None) == "floorpro-file":
            root.removeHandler(handler)
            handler.close()
    configure_logging()


def test_log_has_no_secrets_or_customer_data(client, session, data_dir):
    use_this_tests_log_file()
    make_customer(session, first_name="Peregrine", last_name="Featherstonehaugh")
    client.post("/backups/password", data={"password": SECRET, "password_confirm": SECRET})
    client.post(
        "/backups/password/change",
        data={"current_password": SECRET, "password": NEW_SECRET, "password_confirm": NEW_SECRET},
    )
    client.post("/backups")
    backup_service.change_password(NEW_SECRET, SECRET)
    name = next((data_dir / "backups").glob("*-manual.fpbackup")).name
    client.post(
        f"/backups/local/{name}/restore", data={"confirm": "RESTORE", "password": "wrong guess!"}
    )
    for handler in logging.getLogger().handlers:
        handler.flush()

    log_text = "".join(p.read_text(encoding="utf-8") for p in (data_dir / "logs").glob("*.log*"))
    assert "Backup written" in log_text  # the log is really being written
    key = json.loads((data_dir / "backup-key.json").read_text())["key"]
    for secret in (SECRET, NEW_SECRET, "wrong guess!", key, "Peregrine", "Featherstonehaugh"):
        assert secret not in log_text
    assert base64.b64decode(key).hex() not in log_text
