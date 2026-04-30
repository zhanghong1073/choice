import React, { useMemo, useState } from 'react'
import { Column, Line, Stock } from '@ant-design/plots'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8000'

function fmt(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return '-'
  const n = Number(v)
  if (Math.abs(n) >= 1e9) return `${(n / 1e9).toFixed(2)}B`
  if (Math.abs(n) >= 1e6) return `${(n / 1e6).toFixed(2)}M`
  if (Math.abs(n) >= 1e3) return `${(n / 1e3).toFixed(2)}K`
  return n.toFixed(4).replace(/\.0+$/, '')
}

function Kline({ data }) {
  const points = useMemo(
    () =>
      (data || []).slice(-240).map((d) => ({
        ...d,
        dateLabel: (d.date || '').slice(5), // MM-DD
        trend: Number(d.close) >= Number(d.open) ? '涨' : '跌',
      })),
    [data]
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

  const config = {
    autoFit: true,
    height: 360,
    data: points,
    xField: 'dateLabel',
    yField: ['open', 'close', 'high', 'low'],
    colorField: 'trend',
    color: ({ trend }) => (trend === '涨' ? '#dc2626' : '#16a34a'),
    risingFill: '#dc2626',
    fallingFill: '#16a34a',
    risingStroke: '#dc2626',
    fallingStroke: '#16a34a',
    style: ({ trend }) => ({
      fill: trend === '涨' ? '#dc2626' : '#16a34a',
      stroke: trend === '涨' ? '#dc2626' : '#16a34a',
      fillOpacity: 1,
      strokeOpacity: 1,
      lineWidth: 1,
    }),
    state: {
      active: { style: { lineWidth: 1.2 } },
      inactive: { style: { opacity: 1 } },
    },
    tooltip: {
      title: (d) => `日期: ${d.date}`,
    },
    axis: {
      x: { title: '日期' },
      y: { title: '价格' },
    },
    scale: {
      y: { domain: [priceMin, priceMax] },
    },
    slider: { start: rangeStart, end: 1 },
  }

  const maConfig = {
    autoFit: true,
    height: 360,
    data: maData,
    xField: 'dateLabel',
    yField: 'value',
    seriesField: 'type',
    colorField: 'type',
    scale: {
      color: {
        domain: ['MA5', 'MA10', 'MA20', 'MA60'],
        range: ['#f59e0b', '#06b6d4', '#8b5cf6', '#2563eb'],
      },
      y: { domain: [priceMin, priceMax] },
    },
    smooth: false,
    legend: { position: 'top-left' },
    tooltip: { title: (d) => `日期: ${d.date}` },
    axis: {
      x: false,
      y: false,
    },
    style: {
      lineWidth: 1.5,
    },
    interaction: {
      tooltip: { shared: true },
    },
  }

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
        <Stock {...config} />
        <div className="klineOverlay">
          <Line {...maConfig} />
        </div>
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

  const search = async () => {
    if (!query.trim()) return setMsg('请输入查询内容')
    setLoading(true)
    setMsg('正在拉取真实数据...')
    try {
      const res = await fetch(`${API_BASE}/api/stock/search`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query, period, interval })
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

  return (
    <div className="page">
      <div className="card">
        <h1>美股中文搜索系统</h1>
        <p className="muted">Python FastAPI + React + Vite</p>
        <div className="searchbar">
          <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="输入中文名或Ticker，如 苹果 / NVDA" />
          <select value={period} onChange={(e) => setPeriod(e.target.value)}><option value="3mo">3个月</option><option value="6mo">6个月</option><option value="1y">1年</option><option value="2y">2年</option></select>
          <select value={interval} onChange={(e) => setInterval(e.target.value)}><option value="1d">日K</option><option value="1wk">周K</option></select>
          <button onClick={search} disabled={loading}>{loading ? '查询中...' : '搜索'}</button>
        </div>
        <div className="muted">{msg}</div>
      </div>

      <div className="grid">
        <div className="card"><h3>K线图</h3><Kline data={bundle?.kline || []} /></div>
        <div className="card"><h3>公司资料</h3><KV data={{'股票代码': profile.symbol,'简称': profile.shortName,'全称': profile.longName,'所属板块': profile.sector,'所属行业': profile.industry,'国家/地区': profile.country,'交易所': profile.exchange,'币种': profile.currency,'官网': profile.website,'公司简介': profile.longBusinessSummary}} /></div>
      </div>

      <div className="card"><h3>财务摘要</h3><KV data={{'总市值': fmt(fin.summary?.marketCap),'市盈率(TTM)': fmt(fin.summary?.trailingPE),'预期市盈率': fmt(fin.summary?.forwardPE),'市净率': fmt(fin.summary?.priceToBook),'股息率': fmt(fin.summary?.dividendYield),'净利率': fmt(fin.summary?.profitMargins),'净资产收益率(ROE)': fmt(fin.summary?.returnOnEquity),'负债权益比': fmt(fin.summary?.debtToEquity)}} /></div>
      <div className="card"><h3>利润表（最近期）</h3><Table rows={fin.income_statement} /><h3>资产负债表（最近期）</h3><Table rows={fin.balance_sheet} /><h3>现金流量表（最近期）</h3><Table rows={fin.cashflow} /></div>
    </div>
  )
}
