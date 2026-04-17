import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API_BASE     = 'http://localhost:8000/api';
const API_GENERATE = `${API_BASE}/plannings/generate/`;
const API_STAFF    = `${API_BASE}/staff/`;
const API_SHIFTS   = `${API_BASE}/shifts/`;
const API_SERVICES = `${API_BASE}/services/`;

/**
 * Phase 3 — Génération automatique de planning sur une plage de dates.
 *
 * Améliorations v2 :
 *   - date de début + date de fin (plage multi-jours)
 *   - choix du service par NOM (dropdown), plus par ID
 *   - vue calendrier du planning généré
 *   - score global + détail des contraintes molles
 *   - créneaux non pourvus mis en évidence
 */
export default function GeneratePlanning() {
  const today    = new Date().toISOString().slice(0, 10);
  const tomorrow = new Date(Date.now() + 86400000).toISOString().slice(0, 10);

  const [startDate, setStartDate]   = useState(today);
  const [endDate,   setEndDate]     = useState(tomorrow);
  const [serviceId, setServiceId]   = useState('');
  const [services,  setServices]    = useState([]);
  const [useMeta,   setUseMeta]     = useState(true);
  const [persist,   setPersist]     = useState(true);
  const [loading,   setLoading]     = useState(false);
  const [results,   setResults]     = useState([]);   // tableau, un item par jour
  const [erreur,    setErreur]      = useState(null);
  const [staffMap,  setStaffMap]    = useState({});
  const [shiftMap,  setShiftMap]    = useState({});
  const [calView,   setCalView]     = useState(false); // bascule tableau ↔ calendrier

  // ── Chargement des référentiels ──────────────────────────────────────────
  useEffect(() => {
    Promise.all([
      axios.get(API_STAFF),
      axios.get(API_SHIFTS),
      axios.get(API_SERVICES),
    ]).then(([staff, shifts, svcs]) => {
      const sm = {};
      staff.data.forEach(s => { sm[s.id] = `${s.first_name} ${s.last_name}`; });
      setStaffMap(sm);
      const pm = {};
      shifts.data.forEach(p => { pm[p.id] = p; });
      setShiftMap(pm);
      setServices(svcs.data);
    }).catch(() => {});
  }, []);

  // ── Génération ───────────────────────────────────────────────────────────
  async function generer() {
    if (startDate > endDate) {
      setErreur('⚠️ La date de début doit être antérieure ou égale à la date de fin.');
      return;
    }
    setErreur(null);
    setResults([]);
    setLoading(true);

    // Itère jour par jour sur la plage
    const days = [];
    let cur = new Date(startDate);
    const fin = new Date(endDate);
    while (cur <= fin) {
      days.push(cur.toISOString().slice(0, 10));
      cur.setDate(cur.getDate() + 1);
    }

    const collected = [];
    for (const day of days) {
      try {
        const body = { date: day, metaheuristic: useMeta, persist };
        if (serviceId) body.service_id = parseInt(serviceId, 10);
        const res = await axios.post(API_GENERATE, body);
        collected.push({ day, data: res.data, error: null });
      } catch (err) {
        const msg = err.response?.data?.detail || JSON.stringify(err.response?.data || err.message);
        collected.push({ day, data: null, error: msg });
      }
    }
    setResults(collected);
    setLoading(false);
  }

  // ── Helpers ──────────────────────────────────────────────────────────────
  function fmtTime(dt) {
    if (!dt) return '—';
    return new Date(dt).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
  }
  function fmtDay(dayStr) {
    return new Date(dayStr + 'T12:00:00').toLocaleDateString('fr-FR', {
      weekday: 'short', day: '2-digit', month: 'short',
    });
  }

  // Compile un index day → liste d'affectations pour la vue calendrier
  function buildCalendarData() {
    const cal = {};
    results.forEach(({ day, data }) => {
      if (!data) return;
      cal[day] = data.assignments || [];
    });
    return cal;
  }

  // ── Rendu ────────────────────────────────────────────────────────────────
  const totalCovered  = results.reduce((a, r) => a + (r.data?.summary?.covered   ?? 0), 0);
  const totalUncov    = results.reduce((a, r) => a + (r.data?.summary?.uncovered  ?? 0), 0);
  const totalPersist  = results.reduce((a, r) => a + (r.data?.persisted           ?? 0), 0);
  const avgScore      = results.length
    ? (results.reduce((a, r) => a + (r.data?.score?.total ?? 0), 0) / results.filter(r => r.data).length).toFixed(2)
    : '—';

  return (
    <div>
      <div className="page-header">
        <h1>🤖 Génération automatique du planning</h1>
      </div>

      {/* ── Formulaire ────────────────────────────────────────────────────── */}
      <div className="card" style={{ padding: '1.2rem', marginBottom: '1rem' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
          <div className="form-group">
            <label>📅 Date de début</label>
            <input type="date" value={startDate} onChange={e => setStartDate(e.target.value)} />
          </div>
          <div className="form-group">
            <label>📅 Date de fin</label>
            <input type="date" value={endDate} onChange={e => setEndDate(e.target.value)} />
          </div>
        </div>

        <div className="form-group" style={{ marginTop: '0.8rem' }}>
          <label>🏥 Service (optionnel — laisser vide pour tout l'hôpital)</label>
          <select value={serviceId} onChange={e => setServiceId(e.target.value)}>
            <option value="">— Tous les services —</option>
            {services.map(s => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </div>

        <div style={{ display: 'flex', gap: '2rem', marginTop: '0.8rem', flexWrap: 'wrap' }}>
          <label className="form-group" style={{ margin: 0 }}>
            <input type="checkbox" checked={useMeta} onChange={e => setUseMeta(e.target.checked)} />{' '}
            🧠 Recherche tabou (améliore le score, ~6 s/jour)
          </label>
          <label className="form-group" style={{ margin: 0 }}>
            <input type="checkbox" checked={persist} onChange={e => setPersist(e.target.checked)} />{' '}
            💾 Enregistrer en base après génération
          </label>
        </div>

        <div style={{ marginTop: '1rem', display: 'flex', gap: '1rem', alignItems: 'center' }}>
          <button className="btn btn-primary" onClick={generer} disabled={loading}>
            {loading ? '⏳ Génération en cours…' : '⚙️ Générer le planning'}
          </button>
          {results.length > 0 && (
            <button
              className="btn"
              style={{ background: calView ? '#6c757d' : '#17a2b8', color: '#fff', border: 'none', borderRadius: '6px', padding: '0.5rem 1rem', cursor: 'pointer' }}
              onClick={() => setCalView(v => !v)}
            >
              {calView ? '📋 Vue tableau' : '🗓️ Vue calendrier'}
            </button>
          )}
        </div>
      </div>

      {erreur && <div className="alert alert-error">{erreur}</div>}

      {/* ── Résumé global ──────────────────────────────────────────────────── */}
      {results.length > 0 && (
        <div className="card" style={{ padding: '1rem', marginBottom: '1rem', background: '#f0f7ff', borderLeft: '4px solid #4f8ef7' }}>
          <h2 style={{ marginTop: 0 }}>📊 Résumé global — {results.length} jour(s)</h2>
          <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
            <Kpi label="Shifts couverts"   value={totalCovered}  color="#28a745" />
            <Kpi label="Non pourvus"       value={totalUncov}    color="#dc3545" />
            <Kpi label="Affectations sauvegardées" value={totalPersist} color="#007bff" />
            <Kpi label="Score moyen"       value={avgScore}      color="#fd7e14" note="(↓ meilleur)" />
          </div>
        </div>
      )}

      {/* ── Vue Calendrier ─────────────────────────────────────────────────── */}
      {results.length > 0 && calView && (
        <div className="card" style={{ padding: '1rem', marginBottom: '1rem', overflowX: 'auto' }}>
          <h2 style={{ marginTop: 0 }}>🗓️ Planning — Vue calendrier</h2>
          <CalendarView
            results={results}
            staffMap={staffMap}
            shiftMap={shiftMap}
            fmtDay={fmtDay}
            fmtTime={fmtTime}
          />
        </div>
      )}

      {/* ── Vue tableau jour par jour ──────────────────────────────────────── */}
      {results.length > 0 && !calView && results.map(({ day, data, error }) => (
        <DayCard
          key={day}
          day={day}
          fmtDay={fmtDay}
          fmtTime={fmtTime}
          data={data}
          error={error}
          staffMap={staffMap}
          shiftMap={shiftMap}
        />
      ))}
    </div>
  );
}

/* ────────────────────────────── Sous-composants ──────────────────────────── */

function Kpi({ label, value, color, note }) {
  return (
    <div style={{ textAlign: 'center', minWidth: '120px' }}>
      <div style={{ fontSize: '2rem', fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: '0.8rem', opacity: 0.8 }}>{label}</div>
      {note && <div style={{ fontSize: '0.7rem', opacity: 0.6 }}>{note}</div>}
    </div>
  );
}

function DayCard({ day, fmtDay, fmtTime, data, error, staffMap, shiftMap }) {
  if (error) {
    return (
      <div className="card" style={{ padding: '1rem', marginBottom: '0.8rem', borderLeft: '4px solid #dc3545' }}>
        <h3 style={{ margin: 0 }}>{fmtDay(day)}</h3>
        <div className="alert alert-error" style={{ marginTop: '0.5rem' }}>❌ {error}</div>
      </div>
    );
  }
  if (!data) return null;

  return (
    <div className="card" style={{ padding: '1rem', marginBottom: '0.8rem' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '0.5rem' }}>
        <h3 style={{ margin: 0 }}>📅 {fmtDay(day)}</h3>
        <span style={{ fontSize: '0.85rem', opacity: 0.8 }}>
          Score&nbsp;<b>{data.score.total.toFixed(2)}</b> ·
          Couverts&nbsp;<b style={{ color: '#28a745' }}>{data.summary.covered}</b> /
          {data.summary.shifts_total} ·
          Non pourvus&nbsp;<b style={{ color: '#dc3545' }}>{data.summary.uncovered}</b>
          {data.metaheuristic && ` · Tabou ${data.metaheuristic.iterations} it.`}
        </span>
      </div>

      {data.assignments.length > 0 && (
        <table style={{ marginTop: '0.8rem', width: '100%' }}>
          <thead>
            <tr><th>Créneau</th><th>Horaires</th><th>Soignant</th><th>Légal</th></tr>
          </thead>
          <tbody>
            {data.assignments.map((a, idx) => {
              const sh = shiftMap[a.shift];
              return (
                <tr key={idx}>
                  <td>#{a.shift}{sh ? ` — ${sh.shift_type ?? ''}` : ''}</td>
                  <td>{sh ? `${fmtTime(sh.start_datetime)} → ${fmtTime(sh.end_datetime)}` : '—'}</td>
                  <td>{staffMap[a.staff] || `#${a.staff}`}</td>
                  <td>{a.legal ? '✅' : '❌'}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
      {data.assignments.length === 0 && (
        <p style={{ marginTop: '0.5rem', opacity: 0.6 }}>Aucune nouvelle affectation produite.</p>
      )}

      {data.uncovered.length > 0 && (
        <details style={{ marginTop: '0.8rem' }}>
          <summary style={{ cursor: 'pointer', color: '#dc3545', fontWeight: 600 }}>
            ⚠️ {data.uncovered.length} créneau(x) non pourvu(s)
          </summary>
          <table style={{ marginTop: '0.5rem' }}>
            <thead><tr><th>Shift</th><th>Manque</th><th>Raison</th></tr></thead>
            <tbody>
              {data.uncovered.map((u, idx) => (
                <tr key={idx}>
                  <td>#{u.shift}</td>
                  <td>{u.missing}</td>
                  <td>{u.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </details>
      )}
    </div>
  );
}

function CalendarView({ results, staffMap, shiftMap, fmtDay, fmtTime }) {
  // Regroupe affectations par jour
  const days = results.map(r => r.day);

  const COLORS = [
    '#4f8ef7', '#28a745', '#fd7e14', '#6f42c1', '#17a2b8',
    '#e83e8c', '#20c997', '#ffc107', '#dc3545', '#6c757d',
  ];
  // Couleur stable par soignant
  const staffColors = {};
  let colorIdx = 0;
  function colorFor(staffId) {
    if (!staffColors[staffId]) {
      staffColors[staffId] = COLORS[colorIdx % COLORS.length];
      colorIdx++;
    }
    return staffColors[staffId];
  }

  return (
    <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.min(days.length, 7)}, 1fr)`, gap: '6px', minWidth: '600px' }}>
      {results.map(({ day, data, error }) => (
        <div key={day} style={{ border: '1px solid #dee2e6', borderRadius: '8px', overflow: 'hidden' }}>
          {/* En-tête jour */}
          <div style={{
            background: error ? '#dc3545' : '#4f8ef7',
            color: '#fff',
            padding: '6px 8px',
            fontWeight: 700,
            fontSize: '0.8rem',
            textAlign: 'center',
          }}>
            {fmtDay(day)}
          </div>

          {/* Corps */}
          <div style={{ padding: '6px', minHeight: '80px', background: '#fafbfc' }}>
            {error && <div style={{ color: '#dc3545', fontSize: '0.75rem' }}>Erreur</div>}
            {data && data.assignments.length === 0 && (
              <div style={{ color: '#999', fontSize: '0.75rem', textAlign: 'center', marginTop: '12px' }}>—</div>
            )}
            {data && data.assignments.map((a, idx) => {
              const sh = shiftMap[a.shift];
              return (
                <div
                  key={idx}
                  title={`Shift #${a.shift} | ${sh ? fmtTime(sh.start_datetime) + '→' + fmtTime(sh.end_datetime) : ''}`}
                  style={{
                    background: colorFor(a.staff),
                    color: '#fff',
                    borderRadius: '4px',
                    padding: '2px 5px',
                    marginBottom: '3px',
                    fontSize: '0.72rem',
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {staffMap[a.staff] || `#${a.staff}`}
                  {sh ? ` (${fmtTime(sh.start_datetime)})` : ''}
                </div>
              );
            })}
            {data && data.uncovered.length > 0 && (
              <div style={{
                background: '#fff3cd',
                color: '#856404',
                borderRadius: '4px',
                padding: '2px 5px',
                fontSize: '0.7rem',
                marginTop: '3px',
              }}>
                ⚠️ {data.uncovered.length} non pourvu
              </div>
            )}
          </div>

          {/* Pied score */}
          {data && (
            <div style={{
              background: '#f1f3f5',
              padding: '3px 8px',
              fontSize: '0.7rem',
              textAlign: 'right',
              color: '#555',
            }}>
              Score {data.score.total.toFixed(1)}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
