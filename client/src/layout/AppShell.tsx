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

import type { User } from "../types";

export type NavItem = {
  to: string;
  label: string;
  icon: React.ReactNode;
  badge?: number | string;
  disabled?: boolean;
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
  onLogout,
  children,
}: {
  title: string;
  user: User;
  navItems: NavItem[];
  header?: React.ReactNode;
  actions?: React.ReactNode;
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
            const content = (
              <ListItemButton
                component={NavLink as any}
                to={item.to}
                selected={selectedPrefix === item.to}
                disabled={item.disabled}
                sx={{
                  borderRadius: 2,
                  mb: 0.5,
                  "&.Mui-selected": {
                    backgroundColor: "rgba(37, 99, 235, 0.10)",
                    "&:hover": { backgroundColor: "rgba(37, 99, 235, 0.14)" },
                  },
                }}
                onClick={() => setMobileOpen(false)}
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
            return <Box key={item.to}>{content}</Box>;
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
      <AppBar position="fixed" color="transparent" elevation={0}>
        <Toolbar sx={{ borderBottom: "1px solid", borderColor: "divider", backdropFilter: "blur(10px)" }}>
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
        <Toolbar />
        <Box px={{ xs: 2, md: 3 }} py={3}>
          {children}
        </Box>
      </Box>
    </Box>
  );
}

