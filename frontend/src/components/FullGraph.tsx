// Полный граф знаний — интерактивная страница Pyvis (vis.js), которую бэкенд
// отдаёт на GET /graph/pyvis. Встраиваем во <iframe>: физика, перетаскивание,
// подсветка окрестности при наведении; цитаты и первоисточники — в подсказках.

import { usePhoenix } from "../store";

export function FullGraph() {
  const { apiUrl, health } = usePhoenix();
  const src = `${apiUrl.replace(/\/$/, "")}/graph/pyvis`;

  if (!health) {
    return (
      <div className="grid h-full place-items-center text-sm text-slate-400">
        API недоступен — поднимите бэкенд, чтобы увидеть граф.
      </div>
    );
  }

  return (
    <div className="flex h-full flex-col gap-2">
      <p className="text-xs text-slate-400">
        Наведите курсор на узел — подсветится окрестность; на ребро — цитата и
        первоисточник. Узлы можно перетаскивать, граф масштабируется колесом.
      </p>
      <div className="flex-1 overflow-hidden rounded-xl border border-line bg-surface">
        <iframe
          key={src}
          title="Граф знаний"
          src={src}
          className="h-full w-full"
          style={{ border: 0 }}
        />
      </div>
    </div>
  );
}
