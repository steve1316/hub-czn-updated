import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './i18n'
import './index.css'
import { applyUiScale, loadUiScale } from './lib/ui-scale'

const uiScale = loadUiScale()
if (uiScale !== 1) applyUiScale(uiScale)

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
