/**
 * App - application shell with navigation and routed pages.
 *
 * Element: frontend composition root
 * Implements: FR-AUTH-001; ADR-009
 *
 * Authenticated users get the dashboard shell (sidebar + neutral content
 * wrapper). Unauthenticated users get a centered auth layout without a sidebar.
 * Page components render their own <main>, so the shell wrapper here is a
 * neutral <div> to avoid nested <main> landmarks. Routing behaviour (including
 * the /login -> /chat redirect for authenticated users) is declarative; there
 * is no effect that auto-navigates between pages.
 */
import { Navigate, Route, Routes, useNavigate } from "react-router-dom";
import { useAuth } from "./auth/AuthContext";
import { ProtectedRoute } from "./auth/ProtectedRoute";
import Navigation from "./components/Navigation";
import LoginPage from "./pages/LoginPage";
import ProfilePage from "./pages/ProfilePage";
import ChatPage from "./pages/ChatPage";
import VocabularyPage from "./pages/VocabularyPage";
import ProgressPage from "./pages/ProgressPage";
import type { CefrLevel } from "./api/types";

function AppRoutes({ level }: { level?: CefrLevel }) {
  return (
    <Routes>
      <Route
        path="/login"
        element={<LoginRedirect />}
      />
      <Route
        path="/chat"
        element={
          <ProtectedRoute>
            <ChatPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/vocabulary"
        element={
          <ProtectedRoute>
            <VocabularyPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/progress"
        element={
            <ProtectedRoute>
              <ProgressPage level={level} />
            </ProtectedRoute>
        }
      />
      <Route
        path="/profile"
        element={
          <ProtectedRoute>
            <ProfilePage />
          </ProtectedRoute>
        }
      />
      <Route path="*" element={<LoginRedirect />} />
    </Routes>
  );
}

/** Declarative login redirect; auth state is read, no navigation effect. */
function LoginRedirect() {
  const { user } = useAuth();
  return user ? <Navigate to="/chat" replace /> : <LoginPage />;
}

export default function App() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  if (!user) {
    return (
      <div className="auth-shell">
        <div className="auth-layout">
          <AppRoutes />
        </div>
      </div>
    );
  }

  return (
    <div className="app-shell">
      <Navigation onLogout={() => void logout().then(() => navigate("/login"))} />
      <div className="app-main">
        <AppRoutes level={user.cefr_level} />
      </div>
    </div>
  );
}
