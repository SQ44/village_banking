import { useState } from "react";
import { Alert, Box, Button, Card, CardContent, TextField, Typography } from "@mui/material";

import { Api } from "../api";

export function LoginPage({ busy, onLogin }: { busy: boolean; onLogin: (token: string) => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setError(null);
    try {
      const resp = await Api.login(email.trim(), password);
      onLogin(resp.access_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    }
  };

  return (
    <Box display="flex" alignItems="center" justifyContent="center" height="100%" px={2}>
      <Card sx={{ width: 440 }} variant="outlined">
        <CardContent>
          <Typography variant="h5" gutterBottom>
            Village Banking
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Sign in to continue
          </Typography>
          {error && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {error}
            </Alert>
          )}
          <TextField
            label="Email"
            fullWidth
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            sx={{ mb: 2 }}
            autoComplete="email"
          />
          <TextField
            label="Password"
            type="password"
            fullWidth
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            sx={{ mb: 2 }}
            autoComplete="current-password"
          />
          <Button variant="contained" fullWidth disabled={busy || !email.trim() || !password} onClick={submit}>
            {busy ? "Signing in..." : "Sign in"}
          </Button>
        </CardContent>
      </Card>
    </Box>
  );
}

