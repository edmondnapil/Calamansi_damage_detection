import { Link, Navigate, Route, Routes, useLocation } from "react-router-dom";
import AdminLayout from "./components/AdminLayout";
import Layout from "./components/Layout";
import { EmptyState } from "./components/ui";
import { PublicOnly, RequireAdmin, RequireAuth, RequireSignedIn } from "./lib/auth";
import AdminAccount from "./pages/admin/Account";
import AdminActivity from "./pages/admin/Activity";
import AdminOverview from "./pages/admin/Overview";
import AdminUsers from "./pages/admin/Users";
import { ChangePassword, ForgotPassword, Login, Register, ResetPassword, VerifyEmail } from "./pages/AuthPages";
import Dashboard from "./pages/Dashboard";
import Detect from "./pages/Detect";
import DetectionDetail from "./pages/DetectionDetail";
import Landing from "./pages/Landing";
import Logs from "./pages/Logs";
import Reports from "./pages/Reports";
import Settings from "./pages/Settings";

/** Old bookmarks such as /logs/123 still work: they move under /app. */
function LegacyRedirect() {
  const { pathname, search } = useLocation();
  return <Navigate to={`/app${pathname}${search}`} replace />;
}

export default function App() {
  return (
    <Routes>
      {/* Public */}
      <Route index element={<Landing />} />
      <Route element={<PublicOnly />}>
        <Route path="login" element={<Login />} />
        <Route path="register" element={<Register />} />
        <Route path="forgot-password" element={<ForgotPassword />} />
      </Route>
      <Route path="verify-email" element={<VerifyEmail />} />
      <Route path="reset-password" element={<ResetPassword />} />
      <Route element={<RequireSignedIn />}>
        <Route path="change-password" element={<ChangePassword />} />
      </Route>

      {/* Administrators only: the page guard redirects others, the /api/admin endpoints return 403 */}
      <Route path="admin" element={<RequireAuth />}>
        <Route element={<RequireAdmin />}>
          <Route element={<AdminLayout />}>
            <Route index element={<AdminOverview />} />
            <Route path="users" element={<AdminUsers />} />
            <Route path="activity" element={<AdminActivity />} />
            <Route path="account" element={<AdminAccount />} />
            <Route path="*" element={<Navigate to="/admin" replace />} />
          </Route>
        </Route>
      </Route>

      {/* Signed-in, verified, active accounts only (the API enforces the same) */}
      <Route path="app" element={<RequireAuth />}>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="detect" element={<Detect />} />
          <Route path="logs" element={<Logs />} />
          <Route path="logs/:id" element={<DetectionDetail />} />
          <Route path="reports" element={<Reports />} />
          <Route path="settings" element={<Settings />} />
          <Route path="users" element={<Navigate to="/admin/users" replace />} />
          <Route
            path="*"
            element={
              <EmptyState title="Page not found">
                <Link to="/app" className="font-semibold text-leaf-700 hover:underline">
                  Back to the dashboard
                </Link>
              </EmptyState>
            }
          />
        </Route>
      </Route>

      {["detect", "logs", "logs/:id", "reports", "settings"].map((p) => (
        <Route key={p} path={p} element={<LegacyRedirect />} />
      ))}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
