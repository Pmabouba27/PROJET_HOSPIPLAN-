import React from 'react';
import { BrowserRouter as Router, Routes, Route, NavLink } from 'react-router-dom';
import Soignants from './components/Soignants';
import Postes from './components/Postes';
import Affectations from './components/Affectations';
import './App.css';

function App() {
  return (
    <Router>
      <div className="app">
        {/* Navbar */}
        <nav className="navbar">
          <div className="logo">Hospi<span>Plan</span></div>
          <ul>
            <li><NavLink to="/"           className={({isActive}) => isActive ? "active" : ""}>👨‍⚕️ Soignants</NavLink></li>
            <li><NavLink to="/postes"     className={({isActive}) => isActive ? "active" : ""}>🏥 Postes de garde</NavLink></li>
            <li><NavLink to="/affectations" className={({isActive}) => isActive ? "active" : ""}>📋 Affectations</NavLink></li>
          </ul>
        </nav>

        {/* Pages */}
        <div className="content">
          <Routes>
            <Route path="/"             element={<Soignants />} />
            <Route path="/postes"       element={<Postes />} />
            <Route path="/affectations" element={<Affectations />} />
          </Routes>
        </div>
      </div>
    </Router>
  );
}

export default App;