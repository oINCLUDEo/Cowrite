export const PAGE_SIZE = 20

// «Назад/Далее» для списка документов и истории версий: следующая страница есть, если текущая полная.
export function Pagination({ offset, count, onChange }: { offset: number; count: number; onChange: (offset: number) => void }) {
  return <div className="pagination"><button className="btn-ghost" disabled={!offset} onClick={() => onChange(Math.max(0, offset - PAGE_SIZE))}>Назад</button><button className="btn-ghost" disabled={count < PAGE_SIZE} onClick={() => onChange(offset + PAGE_SIZE)}>Далее</button></div>
}
