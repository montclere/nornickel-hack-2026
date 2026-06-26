"""«Феникс» — фабрика научно-исследовательских гипотез (хакатон-MVP).

Слоистая архитектура с изолированным чистым ядром:

    app/api/             HTTP-граница (FastAPI)
    app/service/         бизнес-логика
        entities.py      доменные сущности (pydantic v2)
        interfaces.py    Protocol-интерфейсы подменяемых зависимостей
        domain/          ЧИСТОЕ ЯДРО без I/O (генераторы/скоринг/карточки)
        pipeline/        use-cases-оркестраторы (зовут infra, кормят domain)
    app/infrastructure/  всё внешнее (OCR/LLM/эмбеддинги/граф/персист) + fakes
    app/container.py     фабрика build(mode): собирает infra и инжектит в pipeline

Фронтенд — отдельный React+Vite-проект в frontend/ (общается с API по HTTP).

Главный инвариант: НИКАКОГО импорта из app.infrastructure / app.api внутри
app.service.domain — это и есть гарантия детерминированности ядра.
"""

__version__ = "0.1.0"
