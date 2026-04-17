import React, { useState } from 'react';
import axios from 'axios';

const API_STATS = 'http://localhost:8000/api/stats/';

/**
 * Tableau de bord statistiques — Phase 3
 *
 * Affiche sur une période choisie :
 *  - Indicateurs globaux (couverture, shifts, absences)
 *  - Répartition par type de garde (barres)
 *  - Stats par service (table + barre de couverture)
 *  - Stats par soignant (shifts, nuits, week-ends, services)
 */
export default function Statistiques() {
  const today  = new Date().toISOString().slice(0, 10);
  const past7  = new Date(Date.now() - 7 * 86400000).toISOString().slice(0, 10);

  const [startDate, setStartDate] = useState(past7);
  const [endDate,   setEndDate]   = useState(today);
  const [data,      setData]      = useState(null);
  const [loading,   setLoading]   = useState(false);
  const [erreur,    setErreur]    = useState(null);

  async function charger() {
    if (startDate > endDate) {
      setErreur('⚠️ La date de début doit être ≤ à la date de fin.');
      return;
    }
    setErreur(null);
    setLoading(true);
    try {
      const res = await axios.get(API_STATS, {
        params: { start_date: startDate, end_date: endDate },
      });
      setData(res.data);
    } catch (err) {
      setErreur(err.response?.data?.detail || 'Erreur lors du chargement des statistiques.');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>📊 Tableau de bord statistiques</h1>
      </div>

      {/* ── Sélection de la période ──────────────────────────────────────── */}
      <div className="card" style={{ padding: '1.2rem', marginBottom: '1.2rem' }}>
        <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', alignItems: 'flex-end' }}>
          <div className="form-group" style={{ margin: 0 }}>
            <label>📅 Début de période</label>
            <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
          </div>
          <div className="form-group" style={{ margin: 0 }}>
            <label>📅 Fin de période</label>
            <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
          </div>
          <button className="btn btn-primary" onClick={charger} disabled={loading}>
            {loading ? '⏳ Chargement…' : '🔍 Afficher les statistiques'}
          </button>
        </div>
        {erreur && <div className="alert alert-error" style={{ marginTop: '0.8rem' }}>{erreur}</div>}
      </div>

      {data && (
        <>
          {/* ── KPIs globaux ─────────────────────────────────────────────── */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '1rem', marginBottom: '1.2rem' }}>
            <KpiCard icon="🏥" label="Créneaux totaux"    value={data.global.total_shifts}       color="#4f8ef7" />
            <KpiCard icon="✅" label="Créneaux couverts"  value={data.global.shifts_covered}      color="#28a745" />
            <KpiCard icon="📈" label="Taux de couverture" value={`${data.global.coverage_rate_pct} %`} color="#fd7e14" />
            <KpiCard icon="📋" label="Affectations"       value={data.global.total_assignments}   color="#6f42c1" />
            <KpiCard icon="🚫" label="Absences actives"   value={data.global.absences_count}      color="#dc3545" />
          </div>

          {/* ── Répartition par type de garde ────────────────────────────── */}
          {data.by_type.length > 0 && (
            <div className="card" style={{ padding: '1rem', marginBottom: '1.2rem' }}>
              <h2 style={{ marginTop: 0 }}>🕐 Répartition par type de garde</h2>
              <BarChart items={data.by_type.map(t => ({ label: t.type, value: t.count }))} />
            </div>
          )}

          {/* ── Stats par service ─────────────────────────────────────────── */}
          <div className="card" style={{ padding: '1rem', marginBottom: '1.2rem' }}>
            <h2 style={{ marginTop: 0 }}>🏥 Couverture par service</h2>
            <table style={{ width: '100%' }}>
              <thead>
                <tr>
                  <th>Service</th>
                  <th>Shifts planifiés</th>
                  <th>Couverts</th>
                  <th style={{ minWidth: '160px' }}>Taux de couverture</th>
                </tr>
              </thead>
              <tbody>
                {data.by_service.map(s => (
                  <tr key={s.name}>
                    <td><b>{s.name}</b></td>
                    <td style={{ textAlign: 'center' }}>{s.total_shifts}</td>
                    <td style={{ textAlign: 'center' }}>{s.covered}</td>
                    <td>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <div style={{
                          flex: 1, height: '12px', background: '#e9ecef', borderRadius: '6px', overflow: 'hidden',
                        }}>
                          <div style={{
                            width: `${s.coverage_pct}%`,
                            height: '100%',
                            background: s.coverage_pct >= 80 ? '#28a745' : s.coverage_pct >= 50 ? '#fd7e14' : '#dc3545',
                            borderRadius: '6px',
                            transition: 'width 0.4s ease',
                          }} />
                        </div>
                        <span style={{ fontSize: '0.85rem', minWidth: '40px' }}>{s.coverage_pct} %</span>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* ── Stats par soignant ────────────────────────────────────────── */}
          <div className="card" style={{ padding: '1rem' }}>
            <h2 style={{ marginTop: 0 }}>👨‍⚕️ Activité par soignant</h2>
            <p style={{ opacity: 0.7, marginTop: 0 }}>
              Période du <b>{startDate}</b> au <b>{endDate}</b> · {data.by_staff.length} soignant(s) actif(s)
            </p>
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%' }}>
                <thead>
                  <tr>
                    <th>Soignant</th>
                    <th>Total gardes</th>
                    <th>Nuits</th>
                    <th>Week-ends</th>
                    <th>Services</th>
                    <th style={{ minWidth: '120px' }}>Charge relative</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_staff.map(s => {
                    const maxTotal = data.by_staff[0]?.total || 1;
                    const pct = Math.round(s.total / maxTotal * 100);
                    return (
                      <tr key={s.id}>
                        <td><b>{s.name}</b></td>
                        <td style={{ textAlign: 'center' }}>{s.total}</td>
                        <td style={{ textAlign: 'center', color: s.nights > 0 ? '#4f8ef7' : 'inherit' }}>
                          {s.nights}
                        </td>
                        <td style={{ textAlign: 'center', color: s.weekends > 0 ? '#fd7e14' : 'inherit' }}>
                          {s.weekends}
                        </td>
                        <td style={{ fontSize: '0.82rem' }}>
                          {s.services.join(', ') || '—'}
                        </td>
                        <td>
                          <div style={{
                            width: '100%', height: '10px', background: '#e9ecef',
                            borderRadius: '5px', overflow: 'hidden',
                          }}>
                            <div style={{
                              width: `${pct}%`, height: '100%',
                              background: '#4f8ef7', borderRadius: '5px',
                            }} />
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </>
      )}

      {!data && !loading && (
        <div className="card" style={{ padding: '2rem', textAlign: 'center', color: '#999' }}>
          <div style={{ fontSize: '3rem' }}>📊</div>
          <p>Sélectionnez une période et cliquez sur « Afficher les statistiques ».</p>
        </div>
      )}
    </div>
  );
}

/* ─────────────────── Composants utilitaires ─────────────────────────────── */

function KpiCard({ icon, label, value, color }) {
  return (
    <div className="card" style={{
      padding: '1rem',
      textAlign: 'center',
      borderTop: `4px solid ${color}`,
    }}>
      <div style={{ fontSize: '1.8rem' }}>{icon}</div>
      <div style={{ fontSize: '1.6rem', fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: '0.8rem', opacity: 0.75, marginTop: '2px' }}>{label}</div>
    </div>
  );
}

function BarChart({ items }) {
  if (!items.length) return <p style={{ opacity: 0.6 }}>Aucune donnée.</p>;
  const max = Math.max(...items.map(i => i.value), 1);
  const COLORS = ['#4f8ef7', '#28a745', '#fd7e14', '#6f42c1', '#17a2b8'];

  return (
    <div style={{ display: 'flex', gap: '1.5rem', alignItems: 'flex-end', padding: '1rem 0', flexWrap: 'wrap' }}>
      {items.map((item, idx) => {
        const h = Math.max(Math.round(item.value / max * 140), 4);
        return (
          <div key={item.label} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px', minWidth: '70px' }}>
            <div style={{ fontWeight: 700, color: COLORS[idx % COLORS.length] }}>{item.value}</div>
            <div style={{
              width: '50px', height: `${h}px`,
              background: COLORS[idx % COLORS.length],
              borderRadius: '4px 4px 0 0',
              transition: 'height 0.3s ease',
            }} />
            <div style={{ fontSize: '0.78rem', textAlign: 'center', wordBreak: 'break-word' }}>{item.label}</div>
          </div>
        );
      })}
    </div>
  );
}
