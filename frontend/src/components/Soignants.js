import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API = 'http://localhost:8000/api/staff/';

export default function Soignants() {
  const [soignants, setSoignants]   = useState([]);
  const [modal, setModal]           = useState(false);
  const [alert, setAlert]           = useState(null);
  const [form, setForm]             = useState({
    id: null, first_name: '', last_name: '',
    email: '', phone: '', is_active: true
  });

  // ── Charger les soignants ──────────────────────────────────
  useEffect(() => { charger(); }, []);

  async function charger() {
    try {
      const res = await axios.get(API);
      setSoignants(res.data);
    } catch { afficherAlerte('error', 'Erreur de chargement'); }
  }

  // ── Ouvrir modal ───────────────────────────────────────────
  function ouvrirModal(s = null) {
    setForm(s
      ? { id: s.id, first_name: s.first_name, last_name: s.last_name,
          email: s.email, phone: s.phone || '', is_active: s.is_active }
      : { id: null, first_name: '', last_name: '', email: '', phone: '', is_active: true }
    );
    setModal(true);
  }

  // ── Sauvegarder ────────────────────────────────────────────
 async function sauvegarder() {
    try {
        if (form.id) {
            await axios.patch(`${API}${form.id}/`, {
                first_name : form.first_name,
                last_name  : form.last_name,
                email      : form.email,
                phone      : form.phone,
                is_active  : form.is_active,
            });
            afficherAlerte('success', 'Soignant modifié !');
        } else {
            await axios.post(API, {
                first_name : form.first_name,
                last_name  : form.last_name,
                email      : form.email,
                phone      : form.phone,
                is_active  : form.is_active,
                roles      : [1],
                specialties: [1],
            });
            afficherAlerte('success', 'Soignant ajouté !');
        }
        setModal(false);
        charger();
    } catch (err) {
        afficherAlerte('error', 'Erreur : ' + JSON.stringify(err.response?.data));
    }
}

  // ── Supprimer ──────────────────────────────────────────────
  async function supprimer(id) {
    if (!window.confirm('Confirmer la suppression ?')) return;
    await axios.delete(`${API}${id}/`);
    afficherAlerte('success', 'Soignant supprimé !');
    charger();
  }

  // ── Alerte ─────────────────────────────────────────────────
  function afficherAlerte(type, msg) {
    setAlert({ type, msg });
    setTimeout(() => setAlert(null), 4000);
  }

  return (
    <div>
      <div className="page-header">
        <h1>👨‍⚕️ Liste des Soignants</h1>
        <button className="btn btn-primary" onClick={() => ouvrirModal()}>
          + Ajouter un soignant
        </button>
      </div>

      {alert && <div className={`alert alert-${alert.type}`}>{alert.msg}</div>}

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>ID</th><th>Nom</th><th>Prénom</th>
              <th>Email</th><th>Téléphone</th><th>Statut</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {soignants.length === 0
              ? <tr><td colSpan="7" className="loading">Chargement...</td></tr>
              : soignants.map(s => (
                <tr key={s.id}>
                  <td>{s.id}</td>
                  <td>{s.last_name}</td>
                  <td>{s.first_name}</td>
                  <td>{s.email}</td>
                  <td>{s.phone || '—'}</td>
                  <td>
                    <span className={`badge ${s.is_active ? 'badge-success' : 'badge-danger'}`}>
                      {s.is_active ? 'Actif' : 'Inactif'}
                    </span>
                  </td>
                  <td>
                    <button className="btn btn-warning" onClick={() => ouvrirModal(s)}>✏️</button>
                    <button className="btn btn-danger"  onClick={() => supprimer(s.id)}>🗑️</button>
                  </td>
                </tr>
              ))
            }
          </tbody>
        </table>
      </div>

      {/* Modal */}
      {modal && (
        <div className="modal-overlay">
          <div className="modal">
            <h2>{form.id ? 'Modifier le soignant' : 'Ajouter un soignant'}</h2>

            <div className="form-group">
              <label>Prénom</label>
              <input value={form.first_name}
                onChange={e => setForm({...form, first_name: e.target.value})} />
            </div>
            <div className="form-group">
              <label>Nom</label>
              <input value={form.last_name}
                onChange={e => setForm({...form, last_name: e.target.value})} />
            </div>
            <div className="form-group">
              <label>Email</label>
              <input type="email" value={form.email}
                onChange={e => setForm({...form, email: e.target.value})} />
            </div>
            <div className="form-group">
              <label>Téléphone</label>
              <input value={form.phone}
                onChange={e => setForm({...form, phone: e.target.value})} />
            </div>
            <div className="form-group">
              <label>Statut</label>
              <select value={form.is_active}
                onChange={e => setForm({...form, is_active: e.target.value === 'true'})}>
                <option value="true">Actif</option>
                <option value="false">Inactif</option>
              </select>
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
