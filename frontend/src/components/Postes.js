import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API_SHIFTS         = 'http://localhost:8000/api/shifts/';
const API_CARE_UNITS     = 'http://localhost:8000/api/care_units/';
const API_SHIFT_TYPES    = 'http://localhost:8000/api/shift_types/';
const API_CERTIFICATIONS = 'http://localhost:8000/api/certifications/';

export default function Postes() {
  const [postes,         setPostes]         = useState([]);
  const [careUnits,      setCareUnits]      = useState([]);
  const [shiftTypes,     setShiftTypes]     = useState([]);
  const [certifications, setCertifications] = useState([]);
  const [modal,          setModal]          = useState(false);
  const [alert,          setAlert]          = useState(null);
  const [form,           setForm]           = useState({
    id: null, care_unit: '', shift_type: '',
    start_datetime: '', end_datetime: '',
    min_staff: 1, max_staff: 5,
    required_certifications: []
  });

  useEffect(() => { charger(); chargerSelects(); }, []);

  async function charger() {
    const res = await axios.get(API_SHIFTS);
    setPostes(res.data);
  }

  async function chargerSelects() {
    const [units, types, certifs] = await Promise.all([
      axios.get(API_CARE_UNITS),
      axios.get(API_SHIFT_TYPES),
      axios.get(API_CERTIFICATIONS)
    ]);
    setCareUnits(units.data);
    setShiftTypes(types.data);
    setCertifications(certifs.data);
  }

  function ouvrirModal(p = null) {
    setForm(p
      ? {
          id: p.id, care_unit: p.care_unit, shift_type: p.shift_type,
          start_datetime: p.start_datetime?.slice(0, 16),
          end_datetime: p.end_datetime?.slice(0, 16),
          min_staff: p.min_staff, max_staff: p.max_staff,
          required_certifications: p.required_certifications || []
        }
      : {
          id: null, care_unit: '', shift_type: '',
          start_datetime: '', end_datetime: '',
          min_staff: 1, max_staff: 5,
          required_certifications: []
        }
    );
    setModal(true);
  }

  function toggleCertification(id) {
    const idNum = parseInt(id);
    const already = form.required_certifications.includes(idNum);
    setForm({
      ...form,
      required_certifications: already
        ? form.required_certifications.filter(c => c !== idNum)
        : [...form.required_certifications, idNum]
    });
  }

  async function sauvegarder() {
    try {
      if (form.id) {
        await axios.patch(`${API_SHIFTS}${form.id}/`, form);
        afficherAlerte('success', 'Poste modifié !');
      } else {
        await axios.post(API_SHIFTS, form);
        afficherAlerte('success', 'Poste ajouté !');
      }
      setModal(false);
      charger();
    } catch (err) {
      afficherAlerte('error', 'Erreur : ' + JSON.stringify(err.response?.data));
    }
  }

  async function supprimer(id) {
    if (!window.confirm('Confirmer la suppression ?')) return;
    await axios.delete(`${API_SHIFTS}${id}/`);
    afficherAlerte('success', 'Poste supprimé !');
    charger();
  }

  function afficherAlerte(type, msg) {
    setAlert({ type, msg });
    setTimeout(() => setAlert(null), 4000);
  }

  return (
    <div>
      <div className="page-header">
        <h1>🏥 Postes de Garde</h1>
        <button className="btn btn-primary" onClick={() => ouvrirModal()}>
          + Ajouter un poste
        </button>
      </div>

      {alert && <div className={`alert alert-${alert.type}`}>{alert.msg}</div>}

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>ID</th><th>Unité</th><th>Type</th>
              <th>Début</th><th>Fin</th><th>Min</th><th>Max</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {postes.length === 0
              ? <tr><td colSpan="8" className="loading">Chargement...</td></tr>
              : postes.map(p => (
                <tr key={p.id}>
                  <td>{p.id}</td>
                  <td>{careUnits.find(u => u.id === p.care_unit)?.name || p.care_unit}</td>
                  <td>{shiftTypes.find(t => t.id === p.shift_type)?.name || p.shift_type}</td>
                  <td>{new Date(p.start_datetime).toLocaleString('fr-FR')}</td>
                  <td>{new Date(p.end_datetime).toLocaleString('fr-FR')}</td>
                  <td>{p.min_staff}</td>
                  <td>{p.max_staff}</td>
                  <td>
                    <button className="btn btn-warning" onClick={() => ouvrirModal(p)}>✏️</button>
                    <button className="btn btn-danger"  onClick={() => supprimer(p.id)}>🗑️</button>
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
            <h2>{form.id ? 'Modifier le poste' : 'Ajouter un poste'}</h2>

            <div className="form-group">
              <label>Unité de soins</label>
              <select value={form.care_unit}
                onChange={e => setForm({...form, care_unit: e.target.value})}>
                <option value="">-- Choisir --</option>
                {careUnits.map(u => <option key={u.id} value={u.id}>{u.name}</option>)}
              </select>
            </div>

            <div className="form-group">
              <label>Type de garde</label>
              <select value={form.shift_type}
                onChange={e => setForm({...form, shift_type: e.target.value})}>
                <option value="">-- Choisir --</option>
                {shiftTypes.map(t => <option key={t.id} value={t.id}>{t.name}</option>)}
              </select>
            </div>

            <div className="form-group">
              <label>Date/heure début</label>
              <input type="datetime-local" value={form.start_datetime}
                onChange={e => setForm({...form, start_datetime: e.target.value})} />
            </div>

            <div className="form-group">
              <label>Date/heure fin</label>
              <input type="datetime-local" value={form.end_datetime}
                onChange={e => setForm({...form, end_datetime: e.target.value})} />
            </div>

            <div className="form-group">
              <label>Minimum soignants</label>
              <input type="number" value={form.min_staff}
                onChange={e => setForm({...form, min_staff: e.target.value})} />
            </div>

            <div className="form-group">
              <label>Maximum soignants</label>
              <input type="number" value={form.max_staff}
                onChange={e => setForm({...form, max_staff: e.target.value})} />
            </div>

            <div className="form-group">
              <label>Certifications requises</label>
              <div style={{
                border: '1px solid #2a2d3e', borderRadius: '6px',
                padding: '0.5rem', maxHeight: '150px',
                overflowY: 'auto', background: '#12141f'
              }}>
                {certifications.map(c => (
                  <label key={c.id} style={{
                    display: 'flex', alignItems: 'center',
                    gap: '0.5rem', padding: '0.3rem',
                    cursor: 'pointer', color: '#d1d5db'
                  }}>
                    <input
                      type="checkbox"
                      checked={form.required_certifications.includes(c.id)}
                      onChange={() => toggleCertification(c.id)}
                    />
                    {c.name}
                  </label>
                ))}
              </div>
              <small style={{color: '#6b7280'}}>
                {form.required_certifications.length} certification(s) sélectionnée(s)
              </small>
            </div>

            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setModal(false)}>Annuler</button>
              <button className="btn btn-success" onClick={sauvegarder}>Sauvegarder</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}