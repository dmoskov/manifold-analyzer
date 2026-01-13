# Manifold Visualization Template

React component template for Manifold Markets analysis visualizations.

## Required Dependencies

```javascript
import React, { useState, useMemo } from 'react';
import { AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from 'recharts';
```

## Component Structure

```jsx
export default function ManifoldAnalysis() {
  const [showTrades, setShowTrades] = useState(true);
  const [showTraders, setShowTraders] = useState(true);
  
  // Data arrays: monthlyData, traders, trades
  // Color mapping object
  // Answer order array (for stacking)
  
  return (
    <div style={{minHeight: '100vh', background: 'linear-gradient(135deg, #0f172a 0%, #1e293b 50%, #0f172a 100%)', color: 'white', padding: 24}}>
      <div style={{maxWidth: 1100, margin: '0 auto'}}>
        {/* Header */}
        {/* Stats Cards */}
        {/* Cumulative Chart */}
        {/* Legend */}
        {/* Trader Leaderboard */}
        {/* Trade List */}
      </div>
    </div>
  );
}
```

## Stats Cards

```jsx
<div style={{display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 24}}>
  {[
    { label: "Total Volume", value: "Ṁ148k", icon: "📊" },
    { label: "Total Trades", value: "330", icon: "🔄" },
    { label: "Peak Month", value: "Oct", icon: "📈" },
    { label: "Current Leader", value: ">$25B", icon: "🎯" },
  ].map((stat, i) => (
    <div key={i} style={{background: 'rgba(51,65,85,0.3)', borderRadius: 12, padding: 12, border: '1px solid rgba(71,85,105,0.5)'}}>
      <div style={{display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4}}>
        <span>{stat.icon}</span>
        <span style={{fontSize: 11, color: '#64748b', textTransform: 'uppercase'}}>{stat.label}</span>
      </div>
      <div style={{fontSize: 18, fontWeight: 700}}>{stat.value}</div>
    </div>
  ))}
</div>
```

## Cumulative Stacked Area Chart

```jsx
// Calculate cumulative data
const cumulativeData = useMemo(() => {
  const answers = Object.keys(colors);
  let running = {};
  answers.forEach(a => running[a] = 0);
  
  return monthlyData.map(m => {
    answers.forEach(a => running[a] += (m[a] || 0));
    return { month: m.month, ...running };
  });
}, []);

// Chart component
<ResponsiveContainer width="100%" height={350}>
  <AreaChart data={cumulativeData}>
    <defs>
      {answerOrder.map(key => (
        <linearGradient key={key} id={`grad-${key.replace(/[<>$.-]/g, '')}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={colors[key]} stopOpacity={0.8} />
          <stop offset="100%" stopColor={colors[key]} stopOpacity={0.3} />
        </linearGradient>
      ))}
    </defs>
    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
    <XAxis dataKey="month" stroke="#64748b" tick={{fill: '#94a3b8', fontSize: 11}} />
    <YAxis stroke="#64748b" tick={{fill: '#94a3b8', fontSize: 11}} tickFormatter={v => `${(v/1000).toFixed(0)}k`} />
    <Tooltip content={<CustomTooltip />} />
    {answerOrder.map(key => (
      <Area key={key} type="monotone" dataKey={key} stackId="1" stroke={colors[key]} fill={`url(#grad-${key.replace(/[<>$.-]/g, '')})`} />
    ))}
  </AreaChart>
</ResponsiveContainer>
```

## Custom Tooltip

```jsx
const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload) return null;
  const total = payload.reduce((sum, p) => sum + (p.value || 0), 0);
  
  return (
    <div style={{background: 'rgba(15,23,42,0.95)', border: '1px solid #334155', borderRadius: 8, padding: 12}}>
      <p style={{color: '#94a3b8', fontSize: 12, marginBottom: 8}}>{label}</p>
      {payload.filter(p => p.value > 0).reverse().map((entry, idx) => (
        <div key={idx} style={{display: 'flex', justifyContent: 'space-between', gap: 16, fontSize: 11, marginBottom: 4}}>
          <div style={{display: 'flex', alignItems: 'center', gap: 6}}>
            <div style={{width: 8, height: 8, borderRadius: '50%', backgroundColor: entry.color}} />
            <span style={{color: '#94a3b8'}}>{entry.dataKey}</span>
          </div>
          <span style={{fontFamily: 'monospace', color: '#e2e8f0'}}>{formatCurrency(entry.value)}</span>
        </div>
      ))}
      <div style={{borderTop: '1px solid #334155', paddingTop: 4, marginTop: 4}}>
        <span style={{color: 'white'}}>Total: {formatCurrency(total)}</span>
      </div>
    </div>
  );
};
```

## Trader Leaderboard Table

```jsx
<table style={{width: '100%', fontSize: 13, borderCollapse: 'collapse'}}>
  <thead>
    <tr style={{borderBottom: '1px solid rgba(71,85,105,0.5)'}}>
      <th style={{textAlign: 'left', padding: 8, color: '#64748b'}}>#</th>
      <th style={{textAlign: 'left', padding: 8, color: '#64748b'}}>Trader</th>
      <th style={{textAlign: 'right', padding: 8, color: '#64748b'}}>Volume</th>
      <th style={{textAlign: 'right', padding: 8, color: '#64748b'}}>Trades</th>
      <th style={{textAlign: 'center', padding: 8, color: '#64748b'}}>Buy/Sell</th>
      <th style={{textAlign: 'right', padding: 8, color: '#64748b'}}>YES Vol</th>
      <th style={{textAlign: 'right', padding: 8, color: '#64748b'}}>NO Vol</th>
      <th style={{textAlign: 'left', padding: 8, color: '#64748b'}}>Top Answers</th>
    </tr>
  </thead>
  <tbody>
    {traders.map((t, i) => (
      <tr key={i} style={{borderBottom: '1px solid rgba(71,85,105,0.2)'}}>
        <td style={{padding: 8, color: i < 3 ? '#fbbf24' : '#94a3b8'}}>
          {i === 0 ? '🥇' : i === 1 ? '🥈' : i === 2 ? '🥉' : i + 1}
        </td>
        <td style={{padding: 8, color: '#e2e8f0', fontWeight: 500}}>{t.name}</td>
        <td style={{padding: 8, textAlign: 'right', fontFamily: 'monospace', color: '#10b981'}}>{formatCurrency(t.total_volume)}</td>
        <td style={{padding: 8, textAlign: 'right', color: '#94a3b8'}}>{t.trade_count}</td>
        <td style={{padding: 8, textAlign: 'center'}}>
          <span style={{color: '#22c55e'}}>{t.buys}</span>/<span style={{color: '#ef4444'}}>{t.sells}</span>
        </td>
        <td style={{padding: 8, textAlign: 'right', fontFamily: 'monospace', color: '#2dd4bf'}}>{formatCurrency(t.yes_volume)}</td>
        <td style={{padding: 8, textAlign: 'right', fontFamily: 'monospace', color: '#fb7185'}}>{formatCurrency(t.no_volume)}</td>
        <td style={{padding: 8}}>
          {t.top_answers.slice(0, 2).map((a, j) => (
            <span key={j} style={{display: 'inline-flex', alignItems: 'center', gap: 4, padding: '2px 6px', background: 'rgba(15,23,42,0.5)', borderRadius: 4, fontSize: 11, marginRight: 4}}>
              <span style={{width: 6, height: 6, borderRadius: '50%', backgroundColor: colors[a.answer]}}></span>
              {a.answer}
            </span>
          ))}
        </td>
      </tr>
    ))}
  </tbody>
</table>
```

## Utility Functions

```jsx
const formatCurrency = (value) => {
  if (value >= 1000) return `Ṁ${(value / 1000).toFixed(1)}k`;
  return `Ṁ${Math.round(value)}`;
};
```

## Styling Notes

- Use dark theme with slate colors (#0f172a, #1e293b, #334155)
- Accent with teal (#2dd4bf, #10b981) for positive/YES
- Rose (#fb7185, #ef4444) for negative/NO  
- Gold (#fbbf24) for top 3 rankings
- Monospace font for numbers
- Subtle borders with rgba transparency
