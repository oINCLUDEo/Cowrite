import { createRoot } from 'react-dom/client'
import { App } from './App'
import './styles.css'

// Монтирование приложения в корневой элемент index.html.
createRoot(document.getElementById('root')!).render(<App />)
