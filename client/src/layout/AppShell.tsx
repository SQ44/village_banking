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

const drawerWidth = 264;

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
  const [mobileOpen, setMobileOpen] = useState(false);
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);

  const selectedPrefix = useMemo(() => {
    const match = navItems.find((item) => location.pathname === item.to || location.pathname.startsWith(`${item.to}/`));
    return match?.to ?? "";
  }, [location.pathname, navItems]);

  const drawer = (
    <Box height="100%" display="flex" flexDirection="column">
      <Box px={2.5} py={2.25}>
        <Typography variant="subtitle1" noWrap>
          {title}
        </Typography>
        <Typography variant="body2" color="text.secondary" noWrap>
          {user.full_name ?? user.email}
        </Typography>
      </Box>
      <Divider />
      <Box flex={1} overflow="auto" py={1}>
        <List sx={{ px: 1.25 }} disablePadding>
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
                  borderRadius: 1.5,
                  mb: 0.25,
                  py: 0.85,
                  color: "text.secondary",
                  "& .MuiListItemIcon-root": { color: "inherit" },
                  "&.Mui-selected": {
                    backgroundColor: "action.selected",
                    color: "text.primary",
                    "&:hover": { backgroundColor: "action.selected" },
                  },
                }}
                onClick={() => {
                  setMobileOpen(false);
                  item.onClick?.();
                }}
              >
                <ListItemIcon sx={{ minWidth: 34, "& svg": { fontSize: 20 } }}>{item.icon}</ListItemIcon>
                <ListItemText
                  primaryTypographyProps={{ fontSize: "0.875rem", fontWeight: 550 }}
                  primary={
                    <Box display="flex" alignItems="center" justifyContent="space-between" gap={1}>
                      <span>{item.label}</span>
                      {item.badge !== undefined && item.badge !== 0 && (
                        <Badge
                          color="primary"
                          badgeContent={item.badge}
                          sx={{ "& .MuiBadge-badge": { borderRadius: 999, position: "static", transform: "none" } }}
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
      <Box px={1.25} py={1}>
        <ListItemButton
          onClick={onLogout}
          sx={{ borderRadius: 1.5, py: 0.85, color: "text.secondary" }}
        >
          <ListItemIcon sx={{ minWidth: 34, color: "inherit", "& svg": { fontSize: 20 } }}>
            <LogoutIcon />
          </ListItemIcon>
          <ListItemText primaryTypographyProps={{ fontSize: "0.875rem", fontWeight: 550 }} primary="Logout" />
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
            minHeight: { xs: 60, md: 64 },
            gap: 1,
            backgroundColor: "background.paper",
            borderBottom: "1px solid",
            borderColor: "divider",
            color: "text.primary",
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
                <IconButton onClick={onToggleColorMode} aria-label="toggle color mode" size="small">
                  {colorMode === "dark" ? <LightModeIcon fontSize="small" /> : <DarkModeIcon fontSize="small" />}
                </IconButton>
              </Tooltip>
            ) : null}
            <Tooltip title="Account">
              <IconButton onClick={(e) => setAnchor(e.currentTarget)} aria-label="account menu" size="small">
                <Avatar sx={{ width: 30, height: 30, fontSize: "0.75rem", bgcolor: "primary.main" }}>
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
            sx={{ "& .MuiDrawer-paper": { width: drawerWidth, backgroundColor: "background.paper" } }}
          >
            {drawer}
          </Drawer>
        )}
        {isDesktop && (
          <Drawer
            variant="permanent"
            open
            sx={{
              "& .MuiDrawer-paper": {
                width: drawerWidth,
                boxSizing: "border-box",
                backgroundColor: "background.paper",
                borderRight: "1px solid",
                borderColor: "divider",
              },
            }}
          >
            {drawer}
          </Drawer>
        )}
      </Box>

      <Box component="main" sx={{ flexGrow: 1, width: { md: `calc(100% - ${drawerWidth}px)` }, minWidth: 0 }}>
        <Toolbar sx={{ minHeight: { xs: 60, md: 64 } }} />
        <Box px={{ xs: 2, md: 3.5 }} py={{ xs: 2.5, md: 3.5 }} maxWidth={1360} mx="auto">
          {children}
        </Box>
      </Box>
    </Box>
  );
}
