import { useState } from 'react'
import './App.css'
import CounterPick from './CounterPick'
import Draft from './Draft'

function App() {
  const [tab, setTab] = useState('draft')

  return (
    <div className="app-shell">
      <h1>롤 밴픽 도우미</h1>
      <div className="tabs">
        <button
          type="button"
          className={tab === 'draft' ? 'tab active' : 'tab'}
          onClick={() => setTab('draft')}
        >
          밴픽 시뮬레이터
        </button>
        <button
          type="button"
          className={tab === 'counter' ? 'tab active' : 'tab'}
          onClick={() => setTab('counter')}
        >
          카운터 픽 검색
        </button>
      </div>

      <div style={{ display: tab === 'draft' ? 'block' : 'none' }}>
        <Draft />
      </div>
      <div style={{ display: tab === 'counter' ? 'block' : 'none' }}>
        <CounterPick />
      </div>
    </div>
  )
}

export default App
