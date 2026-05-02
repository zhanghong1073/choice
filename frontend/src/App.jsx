import React, { useMemo, useState } from 'react'
import { Column } from '@ant-design/plots'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

function fmt(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '-'
  const n = Number(v)
  if (Math.abs(n) >= 1e9) return `${(n / 1e9).toFixed(2)}B`
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(2)}M`
  if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(2)}K`
  return n.toFixed(4).replace(/\.0+$/, '')
}

function Kline({ data, interval }) {
  const points = useMemo(
    () =>
      (data || []).slice(-240).map((d) => ({
        ...d,
        dateLabel:
          interval === '1d' || interval === '1wk'
            ? (d.date || '').slice(5, 10)
            : (d.date || '').replace('T', ' ').slice(5, 16),
        trend: Number(d.close) >= Number(d.open) ? '涨' : '跌',
      })),
    [data, interval]
  )
  if (!points.length) return <div className="empty">暂无K线数据</div>

  const rangeStart = Math.max(0, (points.length - 60) / points.length)
  const priceMin = Math.min(...points.map((d) => d.low))
  const priceMax = Math.max(...points.map((d) => d.high))

  const maData = []
  const maPeriods = [5, 10, 20, 60]
  const calcMA = (n) => {
    for (let i = 0; i < points.length; i++) {
      if (i < n - 1) continue
      const window = points.slice(i - n + 1, i + 1)
      const avg = window.reduce((s, x) => s + Number(x.close || 0), 0) / n
      maData.push({
        date: points[i].date,
        dateLabel: points[i].dateLabel,
        value: Number(avg.toFixed(4)),
        type: `MA${n}`,
      })
    }
  }
  maPeriods.forEach(calcMA)

  const volData = points.map((d) => ({
    date: d.dateLabel,
    volume: Number(d.volume || 0),
    dir: Number(d.close) >= Number(d.open) ? '涨' : '跌',
  }))

  const maColor = {
    MA5: '#f59e0b',
    MA10: '#06b6d4',
    MA20: '#8b5cf6',
    MA60: '#2563eb',
  }
  const w = 1100
  const h = 360
  const left = 56
  const right = 16
  const top = 12
  const bottom = 28
  const plotW = w - left - right
  const plotH = h - top - bottom
  const yScale = (v) => top + ((priceMax - v) * plotH) / (priceMax - priceMin || 1)
  const xScale = (i) => left + (i * plotW) / Math.max(1, points.length - 1)

  const volConfig = {
    autoFit: true,
    height: 170,
    data: volData,
    xField: 'date',
    yField: 'volume',
    colorField: 'dir',
    color: ({ dir }) => (dir === '涨' ? '#dc2626' : '#16a34a'),
    axis: {
      x: { title: '日期' },
      y: { title: '成交量' },
    },
    slider: { start: rangeStart, end: 1 },
  }

  return (
    <div className="klineBlock">
      <div className="klineMain">
        <svg viewBox={`0 0 ${w} ${h}`} className="kline">
          <rect x={left} y={top} width={plotW} height={plotH} fill="#fff" stroke="#e5e7eb" />
          {points.map((d, i) => {
            const x = xScale(i)
            const color = d.trend === '涨' ? '#dc2626' : '#16a34a'
            const yH = yScale(Number(d.high))
            const yL = yScale(Number(d.low))
            const yO = yScale(Number(d.open))
            const yC = yScale(Number(d.close))
            const bodyTop = Math.min(yO, yC)
            const bodyH = Math.max(1, Math.abs(yC - yO))
            const bodyW = Math.max(2, plotW / points.length * 0.6)
            return (
              <g key={`${d.date}-${i}`}>
                <line x1={x} y1={yH} x2={x} y2={yL} stroke={color} strokeWidth="1.2" />
                <rect x={x - bodyW / 2} y={bodyTop} width={bodyW} height={bodyH} fill={color} stroke={color} />
              </g>
            )
          })}
          {Object.keys(maColor).map((name) => {
            const arr = maData.filter((m) => m.type === name)
            if (!arr.length) return null
            const pts = arr.map((m) => {
              const idx = points.findIndex((p) => p.dateLabel === m.dateLabel)
              if (idx < 0) return null
              return `${xScale(idx)},${yScale(Number(m.value))}`
            }).filter(Boolean).join(' ')
            return <polyline key={name} points={pts} fill="none" stroke={maColor[name]} strokeWidth="1.4" />
          })}
        </svg>
      </div>
      <div className="klineVolume">
        <Column {...volConfig} />
      </div>
    </div>
  )
}

function KV({ data }) {
  return (
    <div className="kv">
      {Object.entries(data || {}).map(([k, v]) => (
        <React.Fragment key={k}>
          <div className="k">{k}</div>
          <div>{v || '-'}</div>
        </React.Fragment>
      ))}
    </div>
  )
}

function Table({ rows }) {
  if (!rows?.length) return <div className="empty">暂无数据</div>
  const cols = Object.keys(rows[0])
  return (
    <div className="tableWrap">
      <table>
        <thead><tr>{cols.map((c) => <th key={c}>{c === 'metric' ? '指标' : c}</th>)}</tr></thead>
        <tbody>
          {rows.map((r, idx) => (
            <tr key={idx}>{cols.map((c) => <td key={c}>{c === 'metric' ? r[c] : fmt(r[c])}</td>)}</tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function App() {
  const [query, setQuery] = useState('英伟达')
  const [period, setPeriod] = useState('6mo')
  const [interval, setInterval] = useState('1d')
  const [loading, setLoading] = useState(false)
  const [msg, setMsg] = useState('')
  const [bundle, setBundle] = useState(null)

  const intervalOptions = [
    { label: '30m', value: '30m', period: '5d' },
    { label: '2h', value: '2h', period: '60d' },
    { label: '4h', value: '4h', period: '60d' },
    { label: '1D', value: '1d', period: '6mo' },
    { label: '1W', value: '1wk', period: '2y' },
  ]

  const search = async (override = {}) => {
    const q = (override.query ?? query).trim()
    const p = override.period ?? period
    const iv = override.interval ?? interval
    if (!q) return setMsg('请输入查询内容')
    setLoading(true)
    setMsg('正在拉取真实数据...')
    try {
      const res = await fetch(`${API_BASE}/api/stock/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q, period: p, interval: iv })
      })
      const d = await res.json()
      if (d.error) {
        setMsg(`查询失败: ${d.error}`)
        setBundle(null)
      } else {
        const warn = d.warnings?.length ? ` | 提示: ${d.warnings.join(' ; ')}` : ''
        const source = d.data_source ? ` | 数据源: ${d.data_source}` : ''
        setMsg(`已查询: ${d.query} -> ${d.symbol}，K线点数: ${(d.kline || []).length}${source}${warn}`)
        setBundle(d)
      }
    } catch (e) {
      setMsg(`请求失败: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  const profile = bundle?.profile || {}
  const fin = bundle?.financials || {}

  const onSwitchInterval = (opt) => {
    setInterval(opt.value)
    setPeriod(opt.period)
    search({ interval: opt.value, period: opt.period })
  }

  return (
    <div className="page">
      <div className="card">
        <h1>美股中文搜索系统</h1>
        <div className="searchbar">
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="输入中文名或Ticker，如 苹果 / NVDA" />
          <select value={period} onChange={(e) => setPeriod(e.target.value)}><option value="3mo">3个月</option><option value="6mo">6个月</option><option value="1y">1年</option><option value="2y">2年</option></select>
          <select value={interval} onChange={(e) => setInterval(e.target.value)}><option value="30m">30m</option><option value="2h">2h</option><option value="4h">4h</option><option value="1d">1D</option><option value="1wk">1W</option></select>
          <button onClick={search} disabled={loading}>{loading ? '查询中...' : '搜索'}</button>
        </div>
        <div className="muted">{msg}</div>
      </div>

      <div className="grid">
        <div className="card">
          <div className="klineHeader">
            <h3>K线图</h3>
            <div className="intervalTabs">
              {intervalOptions.map((opt) => (
                <button
                  key={opt.value}
                  className={`tabBtn ${interval === opt.value ? 'active' : ''}`}
                  onClick={() => onSwitchInterval(opt)}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>
          <Kline data={bundle?.kline || []} interval={interval} />
        </div>
        <div className="card"><h3>公司资料</h3><KV data={{'股票代码': profile.symbol,'简称': profile.shortName,'全称': profile.longName,'所属板块': profile.sector,'所属行业': profile.industry,'国家/地区': profile.country,'交易所': profile.exchange,'币种': profile.currency,'官网': profile.website,'公司简介': profile.longBusinessSummary}} /></div>
      </div>

      <div className="card"><h3>财务摘要</h3><KV data={{'总市值': fmt(fin.summary?.marketCap),'市盈率(TTM)': fmt(fin.summary?.trailingPE),'预期市盈率': fmt(fin.summary?.forwardPE),'市净率': fmt(fin.summary?.priceToBook),'股息率': fmt(fin.summary?.dividendYield),'净利率': fmt(fin.summary?.profitMargins),'净资产收益率(ROE)': fmt(fin.summary?.returnOnEquity),'负债权益比': fmt(fin.summary?.debtToEquity)}} /></div>
      <div className="card"><h3>利润表（最近期）</h3><Table rows={fin.income_statement} /><h3>资产负债表（最近期）</h3><Table rows={fin.balance_sheet} /><h3>现金流量表（最近期）</h3><Table rows={fin.cashflow} /></div>
    </div>
  )
}
