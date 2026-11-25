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
export const PlusIcon = () => <Icon d="M12 5v14M5 12h14" />
export const AlertIcon = () => <Icon d="M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0zM12 8v5M12 16h.01" />
// Статус сохранения: облачко, как в Google Docs.
const cloud = 'M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9z'
export const CloudIcon = () => <Icon d={cloud} />
export const CloudCheckIcon = () => <Icon d={`${cloud}M9.5 14.5l2 2 3.5-3.5`} />
export const CloudUploadIcon = () => <Icon d={`${cloud}M12 16.5v-5M9.75 13.75 12 11.5l2.25 2.25`} />
export const CloudOffIcon = () => <Icon d="M3 3l18 18M8.2 6.2A7 7 0 0 0 9 19h8.5c.6 0 1.2-.1 1.7-.3M15.7 10h1.8a4.5 4.5 0 0 1 3.4 7.4M11 5.1a7 7 0 0 1 4.7 4.9" />
// Большой контурный «Cowrite» внизу страницы, обрезанный краем (идея с rokii). Украшение, экранным чтецам не нужен.
// Контур строится фильтром из силуэта залитых букв: у переменного шрифта буквы собраны из перекрывающихся частей,
// и обычная обводка рисует внутренние стыки. Цвет контура задаёт CSS (.wordmark-color).
export function Wordmark() {
  return <footer className="wordmark" aria-hidden="true">
    <svg viewBox="0 0 1000 170">
      <filter id="wordmark-outline">
        <feMorphology in="SourceAlpha" operator="dilate" radius="2.5" result="wide" />
        <feComposite in="wide" in2="SourceAlpha" operator="out" result="ring" />
        <feFlood className="wordmark-color" />
        <feComposite in2="ring" operator="in" />
      </filter>
      <text x="6" y="200" textLength="988" lengthAdjust="spacingAndGlyphs" filter="url(#wordmark-outline)">Cowrite</text>
    </svg>
  </footer>
}

// Знак логотипа — перо.
export const LogoMark = () => <svg aria-hidden="true" focusable="false" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round" strokeLinejoin="round"><path d="M12 19l7-7 3 3-7 7-3-3zM18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5zM2 2l7.586 7.586M13 11a2 2 0 1 1-4 0 2 2 0 0 1 4 0z" /></svg>
export const BulletListIcon = () => <Icon d="M9 6h11M9 12h11M9 18h11M3.5 6h1M3.5 12h1M3.5 18h1" />
export const OrderedListIcon = () => <Icon d="M10 6h10M10 12h10M10 18h10M4 4.5h1.5V9M3.5 9h3M3.8 14.6c.5-.6 2.6-.8 2.6.7 0 1.2-2.6 1.6-2.6 3.2h2.7" />
