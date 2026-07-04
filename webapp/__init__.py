# -*- coding: utf-8 -*-
"""Локальный веб-сервис «Фабрики гипотез» на FastAPI (обёртка над ядром factory).

Плоская слоёная архитектура: interfaces (контракты) → adapters (реализации) →
infra (storage/uploads) → services (оркестрация) → api (routes/schemas) → templates.
Зависимости пробрасываются через DI (webapp/di.py, FastAPI Depends).
НЕ публичный: локальный инстанс для тестирования (см. webapp/config.py, раздел ЛИМИТЫ).
"""
