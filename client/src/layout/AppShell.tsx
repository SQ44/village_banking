import { useMemo, useState } from "react";
import { NavLink, useLocation } from "react-router-dom";
import {
  AppBar,
  Avatar,
  Badge,
  Box,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Menu,
  MenuItem,
  Toolbar,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from "@mui/material";
import MenuIcon from "@mui/icons-material/Menu";
import LogoutIcon from "@mui/icons-material/Logout";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import LightModeIcon from "@mui/icons-material/LightMode";

import type { User } from "../types";

export type NavItem = {
  /** Route to navigate to. Omitted for an item that runs an action instead. */
  to?: string;
  label: string;
  icon: React.ReactNode;
  badge?: number | string;
  disabled?: boolean;
  /** Runs instead of navigating — for actions that live beside the routes. */
  onClick?: () => void;
};

const drawerWidth = 280;

function initials(text: string) {
  const parts = text.trim().split(/\s+/).filter(Boolean);
  const first = parts[0]?.[0] ?? "";
  const second = parts.length > 1 ? parts[parts.length - 1]?.[0] ?? "" : "";
  return (first + second).toUpperCase();
}

export function AppShell({
  title,
  user,
  navItems,
  header,
  actions,
  colorMode,
  onToggleColorMode,
  onLogout,
  children,
}: {
  title: string;
  user: User;
  navItems: NavItem[];
  header?: React.ReactNode;
  actions?: React.ReactNode;
  colorMode?: "light" | "dark";
  onToggleColorMode?: () => void;
  onLogout: () => void;
  children: React.ReactNode;
}) {
  const theme = useTheme();
  const location = useLocation();
  const isDesktop = useMediaQuery(theme.breakpoints.up("md"));
  const isDark = theme.palette.mode === "dark";
  const topBarText = isDark ? "rgba(226,232,240,0.96)" : "text.primary";
  const topBarIcon = isDark ? "rgba(226,232,240,0.92)" : "text.primary";
  const outlinedBorder = isDark ? "rgba(148,163,184,0.6)" : "rgba(37,99,235,0.35)";
  const outlinedHover = isDark ? "rgba(148,163,184,0.12)" : "rgba(37,99,235,0.06)";
  const [mobileOpen, setMobileOpen] = useState(false);
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);

  const selectedPrefix = useMemo(() => {
    const match = navItems.find((item) => location.pathname === item.to || location.pathname.startsWith(`${item.to}/`));
    return match?.to ?? "";
  }, [location.pathname, navItems]);

  const drawer = (
    <Box height="100%" display="flex" flexDirection="column">
      <Box px={2} py={2}>
        <Typography variant="h6">{title}</Typography>
        <Typography variant="body2" color="text.secondary">
          {user.full_name ?? user.email} · {user.role}
        </Typography>
      </Box>
      <Divider />
      <Box flex={1} overflow="auto" py={1}>
        <List sx={{ px: 1 }}>
          {navItems.map((item) => {
            // An action item is a plain button: it has nowhere to navigate to,
            // and must never render as a link or claim the selected state.
            const isAction = !item.to;
            const content = (
              <ListItemButton
                {...(isAction ? {} : { component: NavLink as any, to: item.to })}
                selected={!isAction && selectedPrefix === item.to}
                disabled={item.disabled}
                sx={{
                  borderRadius: 2,
                  mb: 0.5,
                  transition: "background 160ms ease, border-color 160ms ease, transform 160ms ease",
                  "&:hover": { transform: "translateY(-1px)" },
                  "&.Mui-selected": {
                    background:
                      "linear-gradient(90deg, rgba(37,99,235,0.16) 0%, rgba(124,58,237,0.10) 100%)",
                    border: "1px solid rgba(37,99,235,0.18)",
                    "&:hover": {
                      background:
                        "linear-gradient(90deg, rgba(37,99,235,0.20) 0%, rgba(124,58,237,0.12) 100%)",
                    },
                  },
                }}
                onClick={() => {
                  setMobileOpen(false);
                  item.onClick?.();
                }}
              >
                <ListItemIcon sx={{ minWidth: 40 }}>{item.icon}</ListItemIcon>
                <ListItemText
                  primary={
                    <Box display="flex" alignItems="center" justifyContent="space-between" gap={1}>
                      <span>{item.label}</span>
                      {item.badge !== undefined && item.badge !== 0 && (
                        <Badge
                          color="primary"
                          badgeContent={item.badge}
                          sx={{ "& .MuiBadge-badge": { borderRadius: 999 } }}
                        />
                      )}
                    </Box>
                  }
                />
              </ListItemButton>
            );
            return <Box key={item.to ?? item.label}>{content}</Box>;
          })}
        </List>
      </Box>
      <Divider />
      <Box px={1} py={1}>
        <ListItemButton
          onClick={onLogout}
          sx={{
            borderRadius: 2,
            color: theme.palette.error.main,
            "&:hover": { backgroundColor: "rgba(239, 68, 68, 0.06)" },
          }}
        >
          <ListItemIcon sx={{ minWidth: 40, color: theme.palette.error.main }}>
            <LogoutIcon />
          </ListItemIcon>
          <ListItemText primary="Logout" />
        </ListItemButton>
      </Box>
    </Box>
  );

  return (
    <Box display="flex" height="100%">
      <AppBar
        position="fixed"
        color="transparent"
        elevation={0}
        sx={{
          zIndex: (t) => t.zIndex.drawer + 1,
          ml: { md: `${drawerWidth}px` },
          width: { md: `calc(100% - ${drawerWidth}px)` },
        }}
      >
        <Toolbar
          sx={{
            minHeight: { xs: 64, md: 72 },
            py: 1,
            borderBottom: "1px solid",
            borderColor: "divider",
            backdropFilter: "blur(12px)",
            color: topBarText,
            background: isDark
              ? "linear-gradient(90deg, rgba(15,23,42,0.96) 0%, rgba(30,41,59,0.88) 55%, rgba(15,23,42,0.96) 100%)"
              : "linear-gradient(90deg, rgba(37,99,235,0.06) 0%, rgba(124,58,237,0.05) 45%, rgba(255,255,255,0.55) 100%)",
            "& .MuiIconButton-root": { color: topBarIcon },
            "& .MuiButton-root": { color: topBarText },
            "& .MuiButton-contained": {
              color: "common.white",
            },
            "& .MuiButton-outlined": {
              borderColor: outlinedBorder,
              color: topBarText,
            },
            "& .MuiButton-outlined:hover": {
              backgroundColor: outlinedHover,
              borderColor: outlinedBorder,
            },
          }}
        >
          {!isDesktop && (
            <IconButton edge="start" onClick={() => setMobileOpen(true)} aria-label="open navigation">
              <MenuIcon />
            </IconButton>
          )}
          <Box display="flex" alignItems="center" gap={2} flex={1} minWidth={0}>
            {header}
          </Box>
          <Box display="flex" alignItems="center" gap={1}>
            {actions}
            {onToggleColorMode ? (
              <Tooltip title={colorMode === "dark" ? "Switch to light mode" : "Switch to dark mode"}>
                <IconButton onClick={onToggleColorMode} aria-label="toggle color mode">
                  {colorMode === "dark" ? <LightModeIcon /> : <DarkModeIcon />}
                </IconButton>
              </Tooltip>
            ) : null}
            <Tooltip title="Account">
              <IconButton onClick={(e) => setAnchor(e.currentTarget)} aria-label="account menu">
                <Avatar sx={{ width: 34, height: 34, bgcolor: "primary.main" }}>
                  {initials(user.full_name ?? user.email)}
                </Avatar>
              </IconButton>
            </Tooltip>
            <Menu open={!!anchor} anchorEl={anchor} onClose={() => setAnchor(null)}>
              <MenuItem
                onClick={() => {
                  setAnchor(null);
                  onLogout();
                }}
              >
                <LogoutIcon fontSize="small" style={{ marginRight: 8 }} /> Logout
              </MenuItem>
            </Menu>
          </Box>
        </Toolbar>
      </AppBar>

      <Box component="nav" sx={{ width: { md: drawerWidth }, flexShrink: { md: 0 } }}>
        {!isDesktop && (
          <Drawer
            variant="temporary"
            open={mobileOpen}
            onClose={() => setMobileOpen(false)}
            ModalProps={{ keepMounted: true }}
            sx={{ "& .MuiDrawer-paper": { width: drawerWidth } }}
          >
            {drawer}
          </Drawer>
        )}
        {isDesktop && (
          <Drawer variant="permanent" open sx={{ "& .MuiDrawer-paper": { width: drawerWidth, boxSizing: "border-box" } }}>
            {drawer}
          </Drawer>
        )}
      </Box>

      <Box component="main" sx={{ flexGrow: 1, width: { md: `calc(100% - ${drawerWidth}px)` } }}>
        <Toolbar sx={{ minHeight: { xs: 64, md: 72 } }} />
        <Box px={{ xs: 2, md: 3 }} py={{ xs: 2, md: 3 }}>
          {children}
        </Box>
      </Box>
    </Box>
  );
}
