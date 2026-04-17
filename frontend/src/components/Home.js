import React, { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import axios from 'axios';

const API_BASE = 'http://localhost:8000/api';

/**
 * Page d'accueil HospiPlan - Centre Hospitalier Universitaire Saint-Antoine.
 *
 * Regroupe :
 *   - le bandeau d'identité de l'établissement,
 *   - les chiffres-clés en direct (soignants actifs, services, shifts du jour, affectations),
 *   - les tuiles d'action pour les soignants : consulter leurs absences,
 *     déposer des préférences, voir leurs affectations,
 *   - les tuiles d'action pour les RH : générer le planning automatiquement.
 */
export default function Home() {
  const [stats, setStats] = useState({
    staff: null, services: null, shifts: null, assignments: null,
    absences: null, preferences: null,
  });

  useEffect(() => {
    async function fetchAll() {
      try {
        const [staff, services, shifts, assignments, absences, preferences] = await Promise.all([
          axios.get(`${API_BASE}/staff/`),
          axios.get(`${API_BASE}/services/`),
          axios.get(`${API_BASE}/shifts/`),
          axios.get(`${API_BASE}/assignments/`),
          axios.get(`${API_BASE}/absences/`),
          axios.get(`${API_BASE}/preferences/`),
        ]);
        const today = new Date().toISOString().slice(0, 10);
        const todaysShifts = shifts.data.filter(
          s => s.start_datetime && s.start_datetime.slice(0, 10) === today
        );
        setStats({
          staff: staff.data.filter(s => s.is_active).length,
          staff_total: staff.data.length,
          services: services.data.length,
          shifts: todaysShifts.length,
          shifts_total: shifts.data.length,
          assignments: assignments.data.length,
          absences: absences.data.length,
          preferences: preferences.data.length,
        });
      } catch (e) {
        // En cas d'API indisponible, on laisse les stats à null (affichera « — »).
      }
    }
    fetchAll();
  }, []);

  const now = new Date();
  const dateFr = now.toLocaleDateString('fr-FR', {
    weekday: 'long', year: 'numeric', month: 'long', day: 'numeric',
  });

  return (
    <div className="home">
      {/* Bandeau d'accueil */}
      <div className="hero">
        <div className="hero-left">
          <div className="hero-badge">🏥 Établissement</div>
          <h1>Centre Hospitalier Universitaire AL HAMAL </h1>
          <p className="hero-sub">
            Plateforme de gestion du personnel soignant et de planification intelligente des gardes
          </p>
          <p className="hero-date">📅 {dateFr}</p>
        </div>
        <div className="hero-right">
          <div className="hero-card">
            <div className="hero-card-title">HospiPlan · Phase 3</div>
            <div className="hero-card-text">
              Génération automatique du planning<br />respectant <b>100 %</b> des contraintes dures.
            </div>
            <Link to="/generer" className="btn btn-primary">🤖 Générer le planning du jour</Link>
          </div>
        </div>
      </div>

      {/* Chiffres clés */}
      <div className="stats-grid">
        <StatCard icon="👨‍⚕️" label="Soignants actifs"
                  value={stats.staff} hint={stats.staff_total ? `sur ${stats.staff_total}` : ''} />
        <StatCard icon="🏬" label="Services"
                  value={stats.services} />
        <StatCard icon="🕐" label="Shifts aujourd'hui"
                  value={stats.shifts} hint={stats.shifts_total ? `(${stats.shifts_total} au total)` : ''} />
        <StatCard icon="📋" label="Affectations"
                  value={stats.assignments} />
        <StatCard icon="🚫" label="Absences déclarées"
                  value={stats.absences} />
        <StatCard icon="💬" label="Préférences actives"
                  value={stats.preferences} />
      </div>

      {/* Tuiles d'actions */}
      <h2 className="section-title">Espace soignant</h2>
      <div className="actions-grid">
        <ActionTile to="/absences" icon="🚫" title="Déclarer une absence"
                    desc="Signaler un congé, un arrêt maladie ou toute autre indisponibilité." />
        <ActionTile to="/preferences" icon="💬" title="Mes préférences"
                    desc="Exprimer mes préférences de jours, de services ou de types de gardes." />
        <ActionTile to="/affectations" icon="📋" title="Mes affectations"
                    desc="Consulter les gardes qui me sont actuellement attribuées." />
        <ActionTile to="/soignants" icon="👨‍⚕️" title="Annuaire des soignants"
                    desc="Voir l'ensemble de l'équipe, ses rôles et spécialités." />
      </div>

      <h2 className="section-title">Espace RH & planification</h2>
      <div className="actions-grid">
        <ActionTile to="/postes" icon="🏥" title="Postes de garde"
                    desc="Gérer les postes de garde et leurs exigences (certifications, effectif)." />
        <ActionTile to="/generer" icon="🤖" title="Génération automatique"
                    desc="Produire un planning journalier optimisé par heuristique + recherche tabou."
                    highlight />
        <ActionTile to="/affectations" icon="📋" title="Affectations manuelles"
                    desc="Ajuster à la main le planning généré ; les contraintes dures restent appliquées." />
      </div>

      <footer className="home-footer">
        <div>© 2026 AL HAMAL · Hospiplan v3.0</div>
        <div className="home-footer-sub">
         Copyright 
        </div>
      </footer>
    </div>
  );
}

function StatCard({ icon, label, value, hint }) {
  return (
    <div className="stat-card">
      <div className="stat-icon">{icon}</div>
      <div className="stat-value">{value === null || value === undefined ? '—' : value}</div>
      <div className="stat-label">{label}</div>
      {hint && <div className="stat-hint">{hint}</div>}
    </div>
  );
}

function ActionTile({ to, icon, title, desc, highlight }) {
  return (
    <Link to={to} className={`action-tile ${highlight ? 'action-highlight' : ''}`}>
      <div className="action-icon">{icon}</div>
      <div className="action-title">{title}</div>
      <div className="action-desc">{desc}</div>
      <div className="action-arrow">→</div>
    </Link>
  );
}
