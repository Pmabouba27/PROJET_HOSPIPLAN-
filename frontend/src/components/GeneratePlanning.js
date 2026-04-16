import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API_GENERATE = 'http://localhost:8000/api/plannings/generate/';
const API_STAFF    = 'http://localhost:8000/api/staff/';
const API_SHIFTS   = 'http://localhost:8000/api/shifts/';

/**
 * Phase 3 - Composant de génération automatique de planning journalier.
 *
 * Permet de :
 *   - choisir un jour et (optionnellement) un service,
 *   - activer ou non la métaheuristique (recherche tabou),
 *   - lancer la génération via POST /api/plannings/generate/,
 *   - visualiser le planning généré, son score global et le détail par molle,
 *   - voir les créneaux non pourvus (laissés vides quand aucune affectation
 *     légale n'existe, conformément au cahier).
 *
 * Après génération, l'édition manuelle se fait via l'écran Affectations
 * habituel, qui applique déjà les contraintes dures (Phase 2).
 */
export default function GeneratePlanning() {
  const today = new Date().toISOString().slice(0, 10);

  const [date, setDate]               = useState(today);
  const [serviceId, setServiceId]     = useState('');
  const [useMeta, setUseMeta]         = useState(true);
  const [persist, setPersist]         = useState(true);
  const [loading, setLoading]         = useState(false);
  const [result, setResult]           = useState(null);
  const [erreur, setErreur]           = useState(null);
  const [staffMap, setStaffMap]       = useState({});
  const [shiftMap, setShiftMap]       = useState({});

  useEffect(() => {
    Promise.all([axios.get(API_STAFF), axios.get(API_SHIFTS)])
      .then(([staff, shifts]) => {
        const sm = {};
        staff.data.forEach(s => { sm[s.id] = `${s.first_name} ${s.last_name}`; });
        setStaffMap(sm);
        const pm = {};
        shifts.data.forEach(p => { pm[p.id] = p; });
        setShiftMap(pm);
      })
      .catch(() => {});
  }, []);

  async function generer() {
    setErreur(null);
    setResult(null);
    setLoading(true);
    try {
      const body = {
        date,
        metaheuristic: useMeta,
        persist,
      };
      if (serviceId) body.service_id = parseInt(serviceId, 10);
      const res = await axios.post(API_GENERATE, body);
      setResult(res.data);
    } catch (err) {
      const msg = err.response?.data?.detail || JSON.stringify(err.response?.data || err.message);
      setErreur('❌ ' + msg);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div>
      <div className="page-header">
        <h1>🤖 Génération automatique du planning</h1>
      </div>

      <div className="card" style={{ padding: '1rem', marginBottom: '1rem' }}>
        <div className="form-group">
          <label>Jour à planifier</label>
          <input type="date" value={date} onChange={e => setDate(e.target.value)} />
        </div>

        <div className="form-group">
          <label>Service (optionnel — laisser vide pour tout l'hôpital)</label>
          <input
            type="number"
            placeholder="ID service"
            value={serviceId}
            onChange={e => setServiceId(e.target.value)}
          />
        </div>

        <div className="form-group">
          <label>
            <input
              type="checkbox"
              checked={useMeta}
              onChange={e => setUseMeta(e.target.checked)}
            />{' '}
            Appliquer la recherche tabou (améliore le score, ~6 s max)
          </label>
        </div>

        <div className="form-group">
          <label>
            <input
              type="checkbox"
              checked={persist}
              onChange={e => setPersist(e.target.checked)}
            />{' '}
            Enregistrer en base après génération
          </label>
        </div>

        <button className="btn btn-primary" onClick={generer} disabled={loading}>
          {loading ? '⏳ Génération en cours…' : '⚙️ Générer'}
        </button>
      </div>

      {erreur && <div className="alert alert-error">{erreur}</div>}

      {result && (
        <>
          {/* Résumé global */}
          <div className="card" style={{ padding: '1rem', marginBottom: '1rem' }}>
            <h2>Score global</h2>
            <p style={{ fontSize: '1.4rem', margin: '0.5rem 0' }}>
              <b>{result.score.total.toFixed(2)}</b>
              <span style={{ opacity: 0.7, fontSize: '0.9rem' }}> (plus bas = meilleur)</span>
            </p>
            <p>
              Shifts couverts : <b>{result.summary.covered}</b> / {result.summary.shifts_total}{' '}
              — non pourvus : <b>{result.summary.uncovered}</b>{' '}
              — soignants mobilisés : <b>{result.summary.staff_used}</b>{' '}
              — affectations persistées : <b>{result.persisted}</b>
            </p>

            <h3>Détail des pénalités molles</h3>
            <table>
              <thead>
                <tr><th>Contrainte</th><th>Pénalité</th><th>Poids</th></tr>
              </thead>
              <tbody>
                {Object.entries(result.score.details).map(([code, val]) => (
                  <tr key={code}>
                    <td>{code}</td>
                    <td>{val.toFixed(2)}</td>
                    <td>{result.score.weights[code.split('_')[0]] ?? '-'}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            {result.metaheuristic && (
              <p style={{ marginTop: '0.5rem', opacity: 0.8 }}>
                🧭 Tabou : {result.metaheuristic.iterations} itérations,{' '}
                {result.metaheuristic.elapsed_s}s — score final&nbsp;
                {result.metaheuristic.best_score.toFixed(2)}
              </p>
            )}
          </div>

          {/* Affectations produites */}
          <div className="card" style={{ padding: '1rem', marginBottom: '1rem' }}>
            <h2>Affectations générées</h2>
            {result.assignments.length === 0 ? (
              <p>Aucune nouvelle affectation produite.</p>
            ) : (
              <table>
                <thead>
                  <tr><th>Shift</th><th>Soignant</th><th>Légale ?</th></tr>
                </thead>
                <tbody>
                  {result.assignments.map((a, idx) => (
                    <tr key={idx}>
                      <td>
                        #{a.shift}{' '}
                        {shiftMap[a.shift]
                          ? `— ${new Date(shiftMap[a.shift].start_datetime).toLocaleString('fr-FR')}`
                          : ''}
                      </td>
                      <td>{staffMap[a.staff] || `#${a.staff}`}</td>
                      <td>{a.legal ? '✅' : '❌'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>

          {/* Créneaux non pourvus */}
          {result.uncovered.length > 0 && (
            <div className="card" style={{ padding: '1rem' }}>
              <h2>⚠️ Créneaux non pourvus</h2>
              <p style={{ opacity: 0.8 }}>
                Ces shifts n'ont pas trouvé de soignant légal. Laissés vides (conformité Phase 2).
              </p>
              <table>
                <thead>
                  <tr><th>Shift</th><th>Manque</th><th>Raison</th></tr>
                </thead>
                <tbody>
                  {result.uncovered.map((u, idx) => (
                    <tr key={idx}>
                      <td>#{u.shift}</td>
                      <td>{u.missing}</td>
                      <td>{u.reason}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
