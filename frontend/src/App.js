import React from 'react';
import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom';
import Home from './components/Home';
import Soignants from './components/Soignants';
import Postes from './components/Postes';
import Affectations from './components/Affectations';
import GeneratePlanning from './components/GeneratePlanning';
import Absences from './components/Absences';
import Preferences from './components/Preferences';
import Statistiques from './components/Statistiques';
import './App.css';

function App() {
  return (
    <Router>
      <div className="app">
        {/* Navbar */}
        <nav className="navbar">
          <div className="logo">Hospi<span>Plan</span></div>
          <div className="logo-sub">AL AMAL</div>
          <ul>
            <li><NavLink to="/"             end className={({isActive}) => isActive ? "active" : ""}>🏠 Accueil</NavLink></li>
            <li className="nav-section">Espace soignant</li>
            <li><NavLink to="/absences"      className={({isActive}) => isActive ? "active" : ""}>🚫 Absences</NavLink></li>
            <li><NavLink to="/preferences"   className={({isActive}) => isActive ? "active" : ""}>💬 Préférences</NavLink></li>
            <li><NavLink to="/affectations"  className={({isActive}) => isActive ? "active" : ""}>📋 Affectations</NavLink></li>
            <li><NavLink to="/soignants"     className={({isActive}) => isActive ? "active" : ""}>👨‍⚕️ Soignants</NavLink></li>
            <li className="nav-section">Espace RH</li>
            <li><NavLink to="/postes"        className={({isActive}) => isActive ? "active" : ""}>🏥 Postes de garde</NavLink></li>
            <li><NavLink to="/generer"       className={({isActive}) => isActive ? "active" : ""}>🤖 Auto-Planning</NavLink></li>
            <li><NavLink to="/statistiques"  className={({isActive}) => isActive ? "active" : ""}>📊 Statistiques</NavLink></li>
          </ul>
        </nav>

        {/* Pages */}
        <div className="content">
          <Routes>
            <Route path="/"              element={<Home />} />
            <Route path="/soignants"     element={<Soignants />} />
            <Route path="/postes"        element={<Postes />} />
            <Route path="/affectations"  element={<Affectations />} />
            <Route path="/generer"       element={<GeneratePlanning />} />
            <Route path="/absences"      element={<Absences />} />
            <Route path="/preferences"   element={<Preferences />} />
            <Route path="/statistiques"  element={<Statistiques />} />
          </Routes>
        </div>
      </div>
    </Router>
  );
}

export default App;
