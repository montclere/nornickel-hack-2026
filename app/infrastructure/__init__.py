"""Слой infrastructure — всё внешнее: OCR, LLM-извлечение, эмбеддинги, граф,
phrasing, персист, источники, экспорт, агент (LangGraph) + fakes для оффлайна.

Реальные адаптеры реализуют порты из `app.service.interfaces`
и инжектятся в use-cases через `app.container`. Пока готов только пакет `fakes`,
на котором весь pipeline собирается и прогоняется без сети и GPU.
"""
