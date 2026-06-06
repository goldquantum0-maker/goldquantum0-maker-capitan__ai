import { useState } from 'react'
import './App.css'

export default function App() {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100vh', width: '100vw' }}>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: '48px', color: '#00ff88', marginBottom: '20px' }}>⚓</div>
        <h1 style={{ fontSize: '24px', fontWeight: 700, marginBottom: '8px' }}>CAPITAN AI</h1>
        <p style={{ color: '#888', fontSize: '14px' }}>Institutional Research Terminal</p>
        <p style={{ color: '#555', fontSize: '12px', marginTop: '20px' }}>CLOSEAI Technologies</p>
      </div>
    </div>
  )
}