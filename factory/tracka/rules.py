from __future__ import annotations

from dataclasses import dataclass

from factory.tracka.reader import LIBERATED, LOCKED, class_upper_micron
from factory.tracka.schema import DEFAULT_SCHEMA


def _is_fine(size_class: str, threshold_micron: float = DEFAULT_SCHEMA.fine_class_max_micron) -> bool:
    upper = class_upper_micron(size_class)
    return upper is not None and upper <= threshold_micron

FORM_NOTES = {
    "Раскрытый Pnt/Cp": ("извлекаемо", "раскрыт — теряется из-за флотации/классификации, "
                         "не из-за минералогии"),
    "Закрытый Pnt/Cp": ("извлекаемо после раскрытия", "заперт в сростке — нужно доизмельчение"),
    "Миллерит": ("извлекаемо", "Ni-сульфид, флотируется целевой технологией"),
    "Силикатная форма/Валлериит": ("физически не извлекаемо", "Ni в силикатной решётке — "
                                   "текущей флотацией не берётся"),
    "Пирит": ("не целевой минерал", "не несёт извлекаемый Ni/Cu"),
    "Примесь в пирротине": ("трудноизвлекаемо", "Ni рассеян в пирротине — уходит с "
                            "пирротиновым продуктом"),
}

SRC_PRINCIPLE = "Принцип обогащения (раскрытие сростков / извлечение тонких классов)"
SRC_GUIDE = "Инструкция по чтению отчёта института по хвостам"

@dataclass
class Diagnosis:
    family: str
    mechanism: str
    interventions: list
    needs_equipment: bool
    sources: list

def diagnose(dominant_form: str | None, size_class: str) -> Diagnosis | None:
    if dominant_form is None:
        return None
    is_fine = _is_fine(size_class)

    if dominant_form == LOCKED:
        return Diagnosis(
            family="раскрытие / измельчение",
            mechanism=("минерал заперт в сростках (закрытый Pnt/Cp) — не раскрыт "
                       "измельчением; раскрытие делает его доступным флотации"),
            interventions=[
                "Доизмельчение целевого класса в отдельном цикле",
                "Изменение геометрии футеровки шаровых мельниц",
                "Контроль/автокоррекция гранулометрии руды перед мельницами",
                "Замена/донастройка классификаторов (гидроциклоны, песковые насадки)",
            ],
            needs_equipment=True, sources=[SRC_PRINCIPLE, SRC_GUIDE])

    if dominant_form == LIBERATED and is_fine:
        return Diagnosis(
            family="извлечение шламов / классификация",
            mechanism=("минерал раскрыт, но уходит в тонком классе (шламы) — "
                       "текущая схема его не улавливает"),
            interventions=[
                "Тонкое грохочение целевого класса",
                "Гидроциклоны с уменьшением диаметра песковых насадок",
                "Контрольная классификация хвостов и возврат в голову процесса",
                "Магнитная сепарация целевого класса с доизмельчением",
            ],
            needs_equipment=True, sources=[SRC_PRINCIPLE, SRC_GUIDE])

    if dominant_form == LIBERATED:
        return Diagnosis(
            family="доизвлечение флотацией",
            mechanism=("минерал раскрыт, но не доизвлечён — не хватает времени/"
                       "операций флотации"),
            interventions=[
                "Дополнительная (контрольная) флотация класса",
                "Перечистные операции для повышения извлечения",
                "Перераспределение фронта флотации, контактные чаны (время агитации)",
                "Оптимизация плотности пульпы на входе флотации",
                "Корректировка реагентного режима (дозировка собирателя/депрессора)",
            ],
            needs_equipment=False, sources=[SRC_PRINCIPLE, SRC_GUIDE])

    note = FORM_NOTES.get(dominant_form)
    return Diagnosis(
        family="реагентный режим / кинетика флотации",
        mechanism=(f"«{dominant_form}» — отдельный извлекаемый минерал, раскрыт и "
                   f"флотируем, но теряется: вероятно неоптимальный реагентный режим "
                   f"или кинетика флотации именно под эту минеральную форму"
                   + (f" ({note[1]})" if note else "")),
        interventions=[
            f"Подбор/замена собирателя под форму «{dominant_form}» (тип, дозировка)",
            "Оптимизация реагентного режима: pH/Eh, депрессоры породы (пирротин/силикаты)",
            "Увеличение времени флотации / числа контактных операций (медленная кинетика)",
            "Отдельный цикл флотации целевой минеральной формы",
        ],
        needs_equipment=False, sources=[SRC_PRINCIPLE, SRC_GUIDE])
