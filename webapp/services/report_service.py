# -*- coding: utf-8 -*-
"""Чтение результатов прогона для рендера страниц (карточки/деталь/сводка)."""
from __future__ import annotations

from webapp.infra import storage


class ReportService:
    def result(self, run_id: str):
        return storage.load_json(run_id, "result.json")

    def context(self, run_id: str):
        return storage.load_json(run_id, "context.json")

    def metrics(self, run_id: str):
        return storage.load_json(run_id, "metrics.json")

    def fabric(self, run_id: str, fi: int):
        res = self.result(run_id)
        if not res or fi < 0 or fi >= len(res.get("fabrics", [])):
            return None
        return res["fabrics"][fi]

    def hypothesis(self, run_id: str, fi: int, rank: int):
        """Одна гипотеза по индексу фабрики и рангу (для страницы детали)."""
        fab = self.fabric(run_id, fi)
        if not fab:
            return None
        h = next((x for x in fab.get("hypotheses", []) if x.get("rank") == rank), None)
        return (fab, h) if h else None

    def lit_hypothesis(self, run_id: str, rank: int):
        """Гипотеза ветки Б (литература) по рангу — для страницы детали."""
        res = self.result(run_id) or {}
        lit = res.get("literature") or {}
        h = next((x for x in lit.get("hypotheses", []) if x.get("rank") == rank), None)
        return (res, h) if h else None
