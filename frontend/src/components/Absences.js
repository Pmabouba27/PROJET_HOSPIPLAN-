import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API_ABSENCES     = 'http://localhost:8000/api/absences/';
const API_ABSENCE_TYPES = 'http://localhost:8000/api/absence_types/';
const API_STAFF        = 'http://localhost:8000/api/staff/';

/**
 * Page Absences - déclarer et lister les absences d'un soignant.
 *
 * Liste toutes les absences, permet d'en déclarer une nouvelle via une
 * modale (soignant + type + période). Suppression directe via la table.
 */
export default function Absences() {
  const [absences, setAbsences]       = useState([]);
  const [soignants, setSoignants]     = useState([]);
  const [types, setTypes]             = useState([]);
  const [modal, setModal]             = useState(false);
  const [alert, setAlert]             = useState(null);
  const [erreur, setErreur]           = useState(null);
  const [form, setForm]               = useState({
    staff: '', absence_type: '',
    start_date: '', expected_end_date: '',
    is_planned: true,
  });

  useEffect(() => { charger(); chargerSelects(); }, []);

  async function charger() {
    const res = await axios.get(API_ABSENCES);
    setAbsences(res.data);
  }

  async function chargerSelects() {
    try {
      const [staff, types] = await Promise.all([
        axios.get(API_STAFF),
        axios.get(API_ABSENCE_TYPES),
      ]);
      setSoignants(staff.data);
      setTypes(types.data);
    } catch {}
  }

  function ouvrirModal() {
    setForm({
      staff: '', absence_type: '',
      start_date: '', expected_end_date: '',
      is_planned: true,
    });
    setErreur(null);
    setModal(true);
  }

  async function creer() {
    if (!form.staff || !form.absence_type || !form.start_date || !form.expected_end_date) {
      setErreur('❌ Merci de remplir tous les champs obligatoires.');
      return;
    }
    if (form.expected_end_date < form.start_date) {
      setErreur('❌ La date de fin doit être postérieure à la date de début.');
      return;
    }
    try {
      await axios.post(API_ABSENCES, form);
      afficherAlerte('success', 'Absence déclarée.');
      setModal(false);
      charger();
    } catch (err) {
      const msg = err.response?.data?.detail || JSON.stringify(err.response?.data);
      setErreur('❌ ' + msg);
    }
  }

  async function supprimer(id) {
    if (!window.confirm('Supprimer cette absence ?')) return;
    await axios.delete(`${API_ABSENCES}${id}/`);
    afficherAlerte('success', 'Absence supprimée.');
    charger();
  }

  function afficherAlerte(type, msg) {
    setAlert({ type, msg });
    setTimeout(() => setAlert(null), 4000);
  }

  function nomSoignant(id) {
    const s = soignants.find(x => x.id === id);
    return s ? `${s.first_name} ${s.last_name}` : `#${id}`;
  }

  function nomType(id) {
    const t = types.find(x => x.id === id);
    return t ? t.name : `#${id}`;
  }

  return (
    <div>
      <div className="page-header">
        <h1>🚫 Absences</h1>
        <button className="btn btn-primary" onClick={ouvrirModal}>
          + Déclarer une absence
        </button>
      </div>

      {alert && <div className={`alert alert-${alert.type}`}>{alert.msg}</div>}

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>ID</th><th>Soignant</th><th>Type</th>
              <th>Début</th><th>Fin prévue</th><th>Planifiée ?</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {absences.length === 0
              ? <tr><td colSpan="7" className="loading">Aucune absence déclarée.</td></tr>
              : absences.map(a => (
                <tr key={a.id}>
                  <td>{a.id}</td>
                  <td>{nomSoignant(a.staff)}</td>
                  <td>{nomType(a.absence_type)}</td>
                  <td>{a.start_date}</td>
                  <td>{a.expected_end_date}</td>
                  <td>
                    <span className={`badge ${a.is_planned ? 'badge-success' : 'badge-danger'}`}>
                      {a.is_planned ? 'Planifiée' : 'Imprévue'}
                    </span>
                  </td>
                  <td>
                    <button className="btn btn-danger" onClick={() => supprimer(a.id)}>🗑️</button>
                  </td>
                </tr>
              ))
            }
          </tbody>
        </table>
      </div>

      {modal && (
        <div className="modal-overlay">
          <div className="modal">
            <h2>Déclarer une absence</h2>

            <div className="form-group">
              <label>Soignant *</label>
              <select value={form.staff}
                      onChange={e => setForm({...form, staff: e.target.value})}>
                <option value="">-- Choisir --</option>
                {soignants.map(s => (
                  <option key={s.id} value={s.id}>{s.first_name} {s.last_name}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>Type d'absence *</label>
              <select value={form.absence_type}
                      onChange={e => setForm({...form, absence_type: e.target.value})}>
                <option value="">-- Choisir --</option>
                {types.map(t => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>Date de début *</label>
              <input type="date" value={form.start_date}
                     onChange={e => setForm({...form, start_date: e.target.value})} />
            </div>

            <div className="form-group">
              <label>Date de fin prévue *</label>
              <input type="date" value={form.expected_end_date}
                     onChange={e => setForm({...form, expected_end_date: e.target.value})} />
            </div>

            <div className="form-group">
              <label>
                <input type="checkbox" checked={form.is_planned}
                       onChange={e => setForm({...form, is_planned: e.target.checked})} />
                &nbsp;Absence planifiée (ex. congés)
              </label>
            </div>

            {erreur && <div className="alert alert-error">{erreur}</div>}

            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setModal(false)}>Annuler</button>
              <button className="btn btn-success" onClick={creer}>Déclarer</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
