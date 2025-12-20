import { Suspense, lazy, useEffect, useMemo, useState } from "react";
import { Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { Alert, Box, CircularProgress, Snackbar } from "@mui/material";

import { Api } from "./api";
import { LoginPage } from "./pages/LoginPage";
import type { User } from "./types";

const TOKEN_STORAGE_KEY = "vb_token";

const AdminLayout = lazy(() => import("./admin/AdminLayout").then((m) => ({ default: m.AdminLayout })));
const AdminOverviewPage = lazy(() => import("./admin/AdminLayout").then((m) => ({ default: m.AdminOverviewPage })));
const AdminMembersPage = lazy(() => import("./admin/AdminLayout").then((m) => ({ default: m.AdminMembersPage })));
const AdminLoansPage = lazy(() => import("./admin/AdminLayout").then((m) => ({ default: m.AdminLoansPage })));
const AdminRequestsPage = lazy(() => import("./admin/AdminLayout").then((m) => ({ default: m.AdminRequestsPage })));
const AdminSettingsPage = lazy(() => import("./admin/AdminLayout").then((m) => ({ default: m.AdminSettingsPage })));

const MemberLayout = lazy(() => import("./member/MemberLayout").then((m) => ({ default: m.MemberLayout })));
const MemberOverviewPage = lazy(() => import("./member/MemberLayout").then((m) => ({ default: m.MemberOverviewPage })));
const MemberTransactionsPage = lazy(() =>
  import("./member/MemberLayout").then((m) => ({ default: m.MemberTransactionsPage }))
);
const MemberRequestsPage = lazy(() => import("./member/MemberLayout").then((m) => ({ default: m.MemberRequestsPage })));
const MemberMyLoansPage = lazy(() => import("./member/MemberLayout").then((m) => ({ default: m.MemberMyLoansPage })));
const MemberGroupLoansPage = lazy(() =>
  import("./member/MemberLayout").then((m) => ({ default: m.MemberGroupLoansPage }))
);
const MemberSharesPage = lazy(() => import("./member/MemberLayout").then((m) => ({ default: m.MemberSharesPage })));

function FullScreenLoader() {
  return (
    <Box display="flex" alignItems="center" justifyContent="center" height="100%">
      <CircularProgress />
    </Box>
  );
}

export default function App() {
  const navigate = useNavigate();
  const location = useLocation();

  const [token, setToken] = useState<string | null>(() => localStorage.getItem(TOKEN_STORAGE_KEY));
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [authBusy, setAuthBusy] = useState(false);

  const [snack, setSnack] = useState<string | null>(null);
  const onError = (msg: string) => setSnack(msg);

  const logout = () => {
    setToken(null);
    setCurrentUser(null);
    Api.setToken(null);
    localStorage.removeItem(TOKEN_STORAGE_KEY);
    navigate("/login", { replace: true });
  };

  const homePath = useMemo(() => {
    if (!currentUser) return "/login";
    return currentUser.role === "member" ? "/member/overview" : "/admin/overview";
  }, [currentUser]);

  useEffect(() => {
    Api.setToken(token);
    if (!token) {
      setCurrentUser(null);
      return;
    }
    setAuthBusy(true);
    Api.getCurrentUser()
      .then((u) => setCurrentUser(u))
      .catch((err) => {
        setSnack(err instanceof Error ? err.message : "Session expired");
        logout();
      })
      .finally(() => setAuthBusy(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);

  const handleLogin = async (newToken: string) => {
    setAuthBusy(true);
    try {
      Api.setToken(newToken);
      const u = await Api.getCurrentUser();
      localStorage.setItem(TOKEN_STORAGE_KEY, newToken);
      setToken(newToken);
      setCurrentUser(u);
      const next = u.role === "member" ? "/member/overview" : "/admin/overview";
      navigate(next, { replace: true });
    } catch (err) {
      Api.setToken(null);
      setSnack(err instanceof Error ? err.message : "Login failed");
      setToken(null);
      setCurrentUser(null);
      localStorage.removeItem(TOKEN_STORAGE_KEY);
    } finally {
      setAuthBusy(false);
    }
  };

  const requireAuth = (role: "admin" | "member") => {
    if (!token) return <Navigate to="/login" replace state={{ from: location.pathname }} />;
    if (authBusy && !currentUser) return <FullScreenLoader />;
    if (!currentUser) return <Navigate to="/login" replace />;
    if (role === "member" && currentUser.role !== "member") return <Navigate to="/admin/overview" replace />;
    if (role === "admin" && currentUser.role === "member") return <Navigate to="/member/overview" replace />;
    return null;
  };

  return (
    <>
      <Suspense fallback={<FullScreenLoader />}>
        <Routes>
          <Route
            path="/login"
            element={
              token && currentUser ? (
                <Navigate to={homePath} replace />
              ) : (
                <LoginPage busy={authBusy} onLogin={handleLogin} />
              )
            }
          />

          <Route
            path="/admin"
            element={
              requireAuth("admin") ?? <AdminLayout currentUser={currentUser!} onLogout={logout} onError={onError} />
            }
          >
            <Route path="overview" element={<AdminOverviewPage />} />
            <Route path="members" element={<AdminMembersPage />} />
            <Route path="loans" element={<AdminLoansPage />} />
            <Route path="requests" element={<AdminRequestsPage />} />
            <Route path="settings" element={<AdminSettingsPage />} />
            <Route path="*" element={<Navigate to="overview" replace />} />
          </Route>

          <Route
            path="/member"
            element={
              requireAuth("member") ?? <MemberLayout currentUser={currentUser!} onLogout={logout} onError={onError} />
            }
          >
            <Route path="overview" element={<MemberOverviewPage />} />
            <Route path="transactions" element={<MemberTransactionsPage />} />
            <Route path="requests" element={<MemberRequestsPage />} />
            <Route path="my-loans" element={<MemberMyLoansPage />} />
            <Route path="group-loans" element={<MemberGroupLoansPage />} />
            <Route path="shares" element={<MemberSharesPage />} />
            <Route path="*" element={<Navigate to="overview" replace />} />
          </Route>

          <Route path="/" element={<Navigate to={homePath} replace />} />
          <Route path="*" element={<Navigate to={homePath} replace />} />
        </Routes>
      </Suspense>

      <Snackbar open={!!snack} autoHideDuration={6000} onClose={() => setSnack(null)} anchorOrigin={{ vertical: "bottom", horizontal: "center" }}>
        <Alert severity="error" onClose={() => setSnack(null)}>
          {snack}
        </Alert>
      </Snackbar>
    </>
  );
}
