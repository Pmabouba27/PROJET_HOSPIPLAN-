import React, { useState, useEffect } from 'react';
import axios from 'axios';

const API_PREFERENCES = 'http://localhost:8000/api/preferences/';
const API_STAFF       = 'http://localhost:8000/api/staff/';
const API_SHIFT_TYPES = 'http://localhost:8000/api/shift_types/';
const API_SERVICES    = 'http://localhost:8000/api/services/';

const KIND_OPTIONS = [
  { value: 'wants_shift_type',  label: 'Je veux ce type de garde' },
  { value: 'avoids_shift_type', label: 'Je veux éviter ce type de garde' },
  { value: 'wants_day',         label: 'Je veux ce jour de la semaine' },
  { value: 'avoids_day',        label: 'Je veux éviter ce jour de la semaine' },
  { value: 'wants_service',     label: 'Je veux ce service' },
  { value: 'avoids_service',    label: 'Je veux éviter ce service' },
  { value: 'free_text',         label: 'Remarque libre' },
];

const DAYS = [
  { value: 0, label: 'Lundi' }, { value: 1, label: 'Mardi' },
  { value: 2, label: 'Mercredi' }, { value: 3, label: 'Jeudi' },
  { value: 4, label: 'Vendredi' }, { value: 5, label: 'Samedi' },
  { value: 6, label: 'Dimanche' },
];

/**
 * Page Préférences - les soignants y déclarent leurs préférences
 * structurées (F-07). Ces préférences sont ensuite pondérées par leur
 * importance (1 à 5) et interviennent dans la pénalité M2 du générateur
 * automatique.
 */
export default function Preferences() {
  const [prefs, setPrefs]         = useState([]);
  const [soignants, setSoignants] = useState([]);
  const [shiftTypes, setShiftTypes] = useState([]);
  const [services, setServices]   = useState([]);
  const [modal, setModal]         = useState(false);
  const [alert, setAlert]         = useState(null);
  const [erreur, setErreur]       = useState(null);
  const [form, setForm]           = useState(emptyForm());

  function emptyForm() {
    return {
      staff: '',
      kind: 'wants_shift_type',
      importance: 3,
      target_shift_type: '',
      target_service: '',
      target_day_of_week: '',
      description: '',
      is_hard_constraint: false,
      start_date: '',
      end_date: '',
      type: 'user_preference',
    };
  }

  useEffect(() => { charger(); chargerSelects(); }, []);

  async function charger() {
    const res = await axios.get(API_PREFERENCES);
    setPrefs(res.data);
  }

  async function chargerSelects() {
    try {
      const [staff, stypes, services] = await Promise.all([
        axios.get(API_STAFF),
        axios.get(API_SHIFT_TYPES),
        axios.get(API_SERVICES),
      ]);
      setSoignants(staff.data);
      setShiftTypes(stypes.data);
      setServices(services.data);
    } catch {}
  }

  function ouvrirModal() {
    setForm(emptyForm());
    setErreur(null);
    setModal(true);
  }

  async function creer() {
    if (!form.staff) {
      setErreur('❌ Merci de choisir un soignant.');
      return;
    }
    if (['wants_shift_type', 'avoids_shift_type'].includes(form.kind) && !form.target_shift_type) {
      setErreur('❌ Sélectionnez un type de garde.');
      return;
    }
    if (['wants_service', 'avoids_service'].includes(form.kind) && !form.target_service) {
      setErreur('❌ Sélectionnez un service.');
      return;
    }
    if (['wants_day', 'avoids_day'].includes(form.kind) && form.target_day_of_week === '') {
      setErreur('❌ Sélectionnez un jour de la semaine.');
      return;
    }

    const payload = { ...form };
    // Champs vides -> null pour le backend
    ['target_shift_type', 'target_service', 'target_day_of_week', 'start_date', 'end_date']
      .forEach(f => { if (payload[f] === '') payload[f] = null; });
    payload.importance = parseInt(payload.importance, 10) || 1;

    try {
      await axios.post(API_PREFERENCES, payload);
      afficherAlerte('success', 'Préférence enregistrée.');
      setModal(false);
      charger();
    } catch (err) {
      const msg = err.response?.data?.detail || JSON.stringify(err.response?.data);
      setErreur('❌ ' + msg);
    }
  }

  async function supprimer(id) {
    if (!window.confirm('Supprimer cette préférence ?')) return;
    await axios.delete(`${API_PREFERENCES}${id}/`);
    afficherAlerte('success', 'Préférence supprimée.');
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

  function labelKind(k) {
    const o = KIND_OPTIONS.find(x => x.value === k);
    return o ? o.label : k;
  }

  function labelCible(p) {
    if (p.target_shift_type) {
      const st = shiftTypes.find(x => x.id === p.target_shift_type);
      return `Type : ${st ? st.name : `#${p.target_shift_type}`}`;
    }
    if (p.target_service) {
      const sv = services.find(x => x.id === p.target_service);
      return `Service : ${sv ? sv.name : `#${p.target_service}`}`;
    }
    if (p.target_day_of_week !== null && p.target_day_of_week !== undefined) {
      const d = DAYS.find(x => x.value === p.target_day_of_week);
      return `Jour : ${d ? d.label : p.target_day_of_week}`;
    }
    return '—';
  }

  const showShiftType = ['wants_shift_type', 'avoids_shift_type'].includes(form.kind);
  const showService = ['wants_service', 'avoids_service'].includes(form.kind);
  const showDay = ['wants_day', 'avoids_day'].includes(form.kind);

  return (
    <div>
      <div className="page-header">
        <h1>💬 Préférences des soignants</h1>
        <button className="btn btn-primary" onClick={ouvrirModal}>
          + Déposer une préférence
        </button>
      </div>

      {alert && <div className={`alert alert-${alert.type}`}>{alert.msg}</div>}

      <div className="card">
        <table>
          <thead>
            <tr>
              <th>ID</th><th>Soignant</th><th>Préférence</th>
              <th>Cible</th><th>Importance</th><th>Période</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {prefs.length === 0
              ? <tr><td colSpan="7" className="loading">Aucune préférence enregistrée.</td></tr>
              : prefs.map(p => (
                <tr key={p.id}>
                  <td>{p.id}</td>
                  <td>{nomSoignant(p.staff)}</td>
                  <td>{labelKind(p.kind)}</td>
                  <td>{labelCible(p)}</td>
                  <td>{'⭐'.repeat(p.importance || 1)}</td>
                  <td>
                    {p.start_date ? `${p.start_date} → ${p.end_date || '∞'}` : 'Toujours'}
                  </td>
                  <td>
                    <button className="btn btn-danger" onClick={() => supprimer(p.id)}>🗑️</button>
                  </td>
                </tr>
              ))
            }
          </tbody>
        </table>
      </div>

      {modal && (
        <div className="modal-overlay">
          <div className="modal" style={{ width: 560 }}>
            <h2>Déposer une préférence</h2>

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
              <label>Type de préférence *</label>
              <select value={form.kind}
                      onChange={e => setForm({...form, kind: e.target.value,
                                                     target_shift_type: '',
                                                     target_service: '',
                                                     target_day_of_week: ''})}>
                {KIND_OPTIONS.map(o => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>

            {showShiftType && (
              <div className="form-group">
                <label>Type de garde *</label>
                <select value={form.target_shift_type}
                        onChange={e => setForm({...form, target_shift_type: e.target.value})}>
                  <option value="">-- Choisir --</option>
                  {shiftTypes.map(t => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </select>
              </div>
            )}

            {showService && (
              <div className="form-group">
                <label>Service *</label>
                <select value={form.target_service}
                        onChange={e => setForm({...form, target_service: e.target.value})}>
                  <option value="">-- Choisir --</option>
                  {services.map(s => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </div>
            )}

            {showDay && (
              <div className="form-group">
                <label>Jour *</label>
                <select value={form.target_day_of_week}
                        onChange={e => setForm({...form, target_day_of_week: e.target.value})}>
                  <option value="">-- Choisir --</option>
                  {DAYS.map(d => (
                    <option key={d.value} value={d.value}>{d.label}</option>
                  ))}
                </select>
              </div>
            )}

            <div className="form-group">
              <label>Importance (1 = faible, 5 = critique)</label>
              <select value={form.importance}
                      onChange={e => setForm({...form, importance: e.target.value})}>
                {[1,2,3,4,5].map(n => (
                  <option key={n} value={n}>{n} — {'⭐'.repeat(n)}</option>
                ))}
              </select>
            </div>

            <div className="form-group">
              <label>Valable du (optionnel)</label>
              <input type="date" value={form.start_date}
                     onChange={e => setForm({...form, start_date: e.target.value})} />
            </div>
            <div className="form-group">
              <label>Jusqu'au (optionnel)</label>
              <input type="date" value={form.end_date}
                     onChange={e => setForm({...form, end_date: e.target.value})} />
            </div>

            <div className="form-group">
              <label>Remarque libre (optionnel)</label>
              <input type="text" value={form.description}
                     onChange={e => setForm({...form, description: e.target.value})} />
            </div>

            <div className="form-group">
              <label>
                <input type="checkbox" checked={form.is_hard_constraint}
                       onChange={e => setForm({...form, is_hard_constraint: e.target.checked})} />
                &nbsp;Contrainte impérative (Phase 2 — bloque l'affectation)
              </label>
            </div>

            {erreur && <div className="alert alert-error">{erreur}</div>}

            <div className="modal-actions">
              <button className="btn btn-secondary" onClick={() => setModal(false)}>Annuler</button>
              <button className="btn btn-success" onClick={creer}>Enregistrer</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
