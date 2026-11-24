import type { ControlMessage, Role, Version } from './api'

// Подписи интерфейса, которые повторяются в нескольких компонентах.
export const roleLabels: Record<Role, string> = { owner: 'Владелец', editor: 'Редактор', viewer: 'Читатель' }
export const versionKindLabels: Record<Version['kind'], string> = { manual: 'Ручная', scheduled: 'Автоматическая', export: 'Экспорт' }
export const saveStatusLabels: Record<Exclude<ControlMessage['status'], 'role_changed'>, string> = {
  saved: 'Сохранено', unsaved: 'Есть несохранённые изменения', error: 'Ошибка сохранения',
}
export const OFFLINE = 'Нет соединения'
export const connectionLabels = { connecting: 'Подключение…', connected: 'Соединение установлено', disconnected: OFFLINE }
export const formatDateTime = (value: string) => new Date(value).toLocaleString('ru-RU')
