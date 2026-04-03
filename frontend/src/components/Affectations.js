import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API_ASSIGNMENTS = 'http://localhost:8000/api/assignments/';
const API_STAFF       = 'http://localhost:8000/api/staff/';
const API_SHIFTS      = 'http://localhost:8000/api/shifts/';

export default function Affectations() {
  const [affectations, setAffectations] = useState([]);
  const [soignants,    setSoignants]    = useState([]);
  const [postes,       setPostes]       = useState([]);
  const [modal,        setModal]        = useState(false);
  const [alert,        setAlert]        = useState(null);
  const [erreur,       setErreur]       = useState(null);
  const [form,         setForm]         = useState({ staff: '', shift: '' });

  useEffect(() => { charger(); chargerSelects(); }, []);

  async function charger() {
    const res = await axios.get(API_ASSIGNMENTS);
    setAffectations(res.data);
  }

  async function chargerSelects() {
    const [staff, shifts] = await Promise.all([
      axios.get(API_STAFF),
      axios.get(API_SHIFTS)
    ]);
    setSoignants(staff.data);
    setPostes(shifts.data);
  }

  function ouvrirModal() {
    setForm({ staff: '', shift: '' });
    setErreur(null);
    setModal(true);
  }

 async function creerAffectation() {
    // ── Validation côté client ─────────────────────────────
    if (!form.staff || !form.shift) {
        setErreur('❌ Veuillez choisir un soignant et un poste de garde.');
        return;
    }

    try {
        await axios.post(API_ASSIGNMENTS, form);
        afficherAlerte('success', 'Affectation créée !');
        setModal(false);
        charger();
    } catch (err) {
        const msg = err.response?.data?.detail
            || err.response?.data?.non_field_errors
            || JSON.stringify(err.response?.data);
        setErreur('❌ ' + msg);
    }
}
  async function supprimer(id) {
    if (!window.confirm('Supprimer cette affectation ?')) return;
    await axios.delete(`${API_ASSIGNMENTS}${id}/`);
    afficherAlerte('success', 'Affectation supprimée !');
    charger();
  }

  function afficherAlerte(type, msg) {
    setAlert({ type, msg });
    setTimeout(() => setAlert(null), 4000);
  }

  return (
    <div>
      <div className="page-header">
        <h1>📋 Affectations</h1>
        <button className="btn btn-primary" onClick={ouvrirModal}>
          + Créer une affectation
        </button>
      </div>

      {alert && <div className={`alert alert-${alert.type}`}>{alert.msg}</div>}

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>ID</th><th>Soignant</th><th>Poste</th><th>Date</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {affectations.length === 0
              ? <tr><td colSpan="5" className="loading">Chargement...</td></tr>
              : affectations.map(a => {
                const soignant = soignants.find(s => s.id === a.staff);
                const poste    = postes.find(p => p.id === a.shift);
                return (
                  <tr key={a.id}>
                    <td>{a.id}</td>
                    <td>{soignant ? `${soignant.first_name} ${soignant.last_name}` : a.staff}</td>
                    <td>{poste ? `Poste #${poste.id} — ${new Date(poste.start_datetime).toLocaleDateString('fr-FR')}` : a.shift}</td>
                    <td>{new Date(a.assigned_at).toLocaleString('fr-FR')}</td>
                    <td>
                      <button className="btn btn-danger" onClick={() => supprimer(a.id)}>🗑️</button>
                    </td>
                  </tr>
                );
              })
            }
          </tbody>
        </table>
      </div>

      {modal && (
        <div className="modal-overlay">
          <div className="modal">
            <h2>Créer une affectation</h2>

            <div className="form-group">
              <label>Soignant</label>
              <select value={form.staff}
                onChange={e => setForm({...form, staff: e.target.value})}>
                <option value="">-- Choisir un soignant --</option>
                {soignants.map(s => (
                  <option key={s.id} value={s.id}>
                    {s.first_name} {s.last_name}
                  </option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>Poste de garde</label>
              <select value={form.shift}
                onChange={e => setForm({...form, shift: e.target.value})}>
                <option value="">-- Choisir un poste --</option>
                {postes.map(p => (
                  <option key={p.id} value={p.id}>
                    Poste #{p.id} — {new Date(p.start_datetime).toLocaleString('fr-FR')}
                  </option>
                ))}
              </select>
            </div>

            {erreur && <div className="alert alert-error">{erreur}</div>}

            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setModal(false)}>Annuler</button>
              <button className="btn btn-success" onClick={creerAffectation}>Affecter</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}