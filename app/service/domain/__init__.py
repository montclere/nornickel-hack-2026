"""ЧИСТОЕ ЯДРО домена — детерминированная логика без I/O.

Разрешено импортировать: pydantic / networkx / numpy / sklearn, `app.service.entities`,
`app.service.interfaces`, `app.service.errors` и данные.

ЗАПРЕЩЕНО импортировать `app.infrastructure` и `app.api` — этот инвариант проверяется
тестом изоляции (tests/test_isolation.py) и контрактом import-linter. Именно он даёт
гарантию «тот же граф → тот же результат»: ядро физически не может позвать LLM/сеть/БД.
"""
