import type { ControlMessage, Role, Version } from './api'

// Подписи интерфейса, которые повторяются в нескольких компонентах.
export const roleLabels: Record<Role, string> = { owner: 'Владелец', editor: 'Редактор', viewer: 'Читатель' }
export const versionKindLabels: Record<Version['kind'], string> = { manual: 'Сохранена вручную', scheduled: 'Автосохранение', export: 'Экспорт в PDF' }
// Статус в шапке: цвет точки по смыслу (VIS-3), полная формулировка во всплывающей подсказке.
export type SaveState = Exclude<ControlMessage['status'], 'role_changed'> | 'syncing' | 'offline' | 'connecting'
export const saveStateLabels: Record<SaveState, [text: string, hint: string]> = {
  connecting: ['Подключаемся…', 'Подключаемся к серверу'],
  syncing: ['Сохраняем…', 'Проверяем, всё ли сохранено'],
  unsaved: ['Сохраняем…', 'Изменения отправляются на сервер'],
  saved: ['Сохранено', 'Все изменения сохранены на сервере'],
  error: ['Не удалось сохранить', 'Сервер не смог сохранить изменения'],
  offline: ['Нет соединения', 'Нет связи с сервером: изменения пока только в этой вкладке'],
}
export const formatDateTime = (value: string) => new Date(value).toLocaleString('ru-RU')
export const formatTime = (value: string) => new Date(value).toLocaleTimeString('ru-RU', { hour: '2-digit', minute: '2-digit' })

// «Сегодня», «Вчера» или «22 ноября» по местному времени браузера.
export function formatDay(value: string): string {
  const date = new Date(value)
  const days = Math.round((new Date(new Date().toDateString()).getTime() - new Date(date.toDateString()).getTime()) / 86_400_000)
  return days === 0 ? 'Сегодня' : days === 1 ? 'Вчера' : date.toLocaleDateString('ru-RU', { day: 'numeric', month: 'long' })
}
