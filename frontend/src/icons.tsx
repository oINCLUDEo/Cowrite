// Иконки 24×24 обводкой. Подпись даёт кнопка, поэтому сами иконки скрыты от экранных чтецов.
function Icon({ d, width = 2 }: { d: string; width?: number }) {
  return <svg aria-hidden="true" focusable="false" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={width} strokeLinecap="round" strokeLinejoin="round"><path d={d} /></svg>
}

export const BackIcon = () => <Icon d="M15 18l-6-6 6-6" />
export const HistoryIcon = () => <Icon d="M3 12a9 9 0 1 0 3-6.7L3 8M3 3v5h5M12 7v5l3 2" />
export const DownloadIcon = () => <Icon d="M12 4v11M7 10l5 5 5-5M5 20h14" />
export const ShareIcon = () => <Icon d="M13 8a4 4 0 1 1-8 0 4 4 0 0 1 8 0M2 21c0-3.9 3.1-7 7-7s7 3.1 7 7M19 8v6M16 11h6" />
export const MoreIcon = () => <Icon d="M5 12h.01M12 12h.01M19 12h.01" width={3} />
export const BookmarkPlusIcon = () => <Icon d="M19 21l-7-4-7 4V5a2 2 0 0 1 2-2h10a2 2 0 0 1 2 2zM12 7v6M9 10h6" />
export const CloseIcon = () => <Icon d="M6 6l12 12M18 6L6 18" />
