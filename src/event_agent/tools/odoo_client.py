"""Заготовка для будущей записи извлечённых событий в Odoo.

Пока намеренно не используется в графе (см. README, раздел Roadmap).
Когда будете готовы подключать запись, добавьте отдельный узел `odoo_write`
в builder.py, который будет вызывать create_record() для каждой валидной EventRecord.
"""
import xmlrpc.client
from event_agent.config import settings


class OdooClient:
    def __init__(self):
        self._common = xmlrpc.client.ServerProxy(f"{settings.odoo_url}/xmlrpc/2/common")
        self._models = xmlrpc.client.ServerProxy(f"{settings.odoo_url}/xmlrpc/2/object")
        self._uid = None

    def _authenticate(self) -> int:
        if self._uid is None:
            self._uid = self._common.authenticate(
                settings.odoo_db, settings.odoo_username, settings.odoo_password, {}
            )
        return self._uid

    def create_record(self, model: str, values: dict) -> int:
        uid = self._authenticate()
        return self._models.execute_kw(
            settings.odoo_db, uid, settings.odoo_password, model, "create", [values]
        )
