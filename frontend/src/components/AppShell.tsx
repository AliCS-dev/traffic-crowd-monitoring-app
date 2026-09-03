import { useState } from "react";
import {
  AppBar,
  Box,
  Divider,
  Drawer,
  IconButton,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Tooltip,
  Typography,
  useMediaQuery,
} from "@mui/material";
import { useTheme } from "@mui/material/styles";
import {
  Activity,
  ChartNoAxesCombined,
  History,
  Info,
  Menu,
  ScanSearch,
} from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { ApplicationInfoDialog } from "./ApplicationInfoDialog.tsx";
import { BackendStatus } from "./BackendStatus.tsx";

const drawerWidth = 232;

const navigation = [
  { label: "Workspace", to: "/workspace", icon: ScanSearch },
  { label: "Sessions", to: "/sessions", icon: History },
  { label: "Results", to: "/analyses", icon: ChartNoAxesCombined },
];

function getPageTitle(pathname: string): string {
  if (pathname.startsWith("/sessions")) return "Sessions";
  if (pathname.startsWith("/analyses")) return "Results";
  if (pathname.startsWith("/workspace")) return "Workspace";
  return "Page not found";
}

export function AppShell() {
  const [mobileNavigationOpen, setMobileNavigationOpen] = useState(false);
  const [informationOpen, setInformationOpen] = useState(false);
  const theme = useTheme();
  const desktopNavigation = useMediaQuery(theme.breakpoints.up("md"));
  const location = useLocation();

  const navigationContent = (
    <>
      <Toolbar sx={{ gap: 1.25, minHeight: 64 }}>
        <Box
          sx={{
            display: "grid",
            width: 30,
            height: 30,
            placeItems: "center",
            flex: "0 0 auto",
            borderRadius: 1,
            bgcolor: "primary.main",
            color: "primary.contrastText",
          }}
        >
          <Activity aria-hidden size={19} strokeWidth={2.2} />
        </Box>
        <Typography
          component="span"
          noWrap
          sx={{ fontWeight: 750, lineHeight: 1.2 }}
        >
          Traffic Monitor
        </Typography>
      </Toolbar>
      <Divider />
      <List aria-label="Primary navigation" sx={{ px: 1.5, py: 2 }}>
        {navigation.map(({ label, to, icon: Icon }) => (
          <ListItemButton
            component={NavLink}
            key={to}
            onClick={() => setMobileNavigationOpen(false)}
            sx={{
              minHeight: 44,
              mb: 0.5,
              borderRadius: 1,
              color: "text.secondary",
              "&.active": {
                bgcolor: "primary.light",
                color: "primary.dark",
                "& .MuiListItemIcon-root": { color: "primary.dark" },
              },
            }}
            to={to}
          >
            <ListItemIcon sx={{ minWidth: 38, color: "inherit" }}>
              <Icon aria-hidden size={19} strokeWidth={1.9} />
            </ListItemIcon>
            <ListItemText
              primary={label}
              slotProps={{
                primary: { sx: { fontSize: 14, fontWeight: 650 } },
              }}
            />
          </ListItemButton>
        ))}
      </List>
    </>
  );

  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      <Box
        component="a"
        href="#main-content"
        sx={{
          position: "fixed",
          top: 8,
          left: 8,
          zIndex: (currentTheme) => currentTheme.zIndex.tooltip + 1,
          transform: "translateY(-160%)",
          bgcolor: "text.primary",
          color: "background.paper",
          px: 1.5,
          py: 1,
          borderRadius: 1,
          textDecoration: "none",
          "&:focus": { transform: "translateY(0)" },
        }}
      >
        Skip to content
      </Box>
      <AppBar
        color="inherit"
        position="fixed"
        sx={{
          ml: { md: `${drawerWidth}px` },
          width: { md: `calc(100% - ${drawerWidth}px)` },
          borderBottom: "1px solid",
          borderColor: "divider",
          boxShadow: "none",
        }}
      >
        <Toolbar sx={{ gap: 1.5, minHeight: 64 }}>
          <Tooltip title="Open navigation">
            <IconButton
              aria-label="Open navigation"
              edge="start"
              onClick={() => setMobileNavigationOpen(true)}
              sx={{ display: { md: "none" } }}
            >
              <Menu aria-hidden size={21} />
            </IconButton>
          </Tooltip>
          <Typography component="p" sx={{ flexGrow: 1 }} variant="h2">
            {getPageTitle(location.pathname)}
          </Typography>
          <BackendStatus />
          <Tooltip title="Application information">
            <IconButton
              aria-label="Application information"
              onClick={() => setInformationOpen(true)}
              size="small"
            >
              <Info aria-hidden size={20} />
            </IconButton>
          </Tooltip>
        </Toolbar>
      </AppBar>

      <Box
        aria-label="Primary navigation"
        component="nav"
        sx={{ width: { md: drawerWidth }, flexShrink: 0 }}
      >
        <Drawer
          open={mobileNavigationOpen}
          onClose={() => setMobileNavigationOpen(false)}
          slotProps={{ paper: { sx: { width: drawerWidth } } }}
          sx={{ display: { xs: "block", md: "none" } }}
          variant="temporary"
        >
          {navigationContent}
        </Drawer>
        <Drawer
          open={desktopNavigation}
          slotProps={{
            paper: {
              sx: {
                width: drawerWidth,
                boxSizing: "border-box",
                borderRightColor: "divider",
              },
            },
          }}
          sx={{ display: { xs: "none", md: "block" } }}
          variant="permanent"
        >
          {navigationContent}
        </Drawer>
      </Box>

      <Box
        component="main"
        id="main-content"
        tabIndex={-1}
        sx={{
          flexGrow: 1,
          width: { xs: "100%", md: `calc(100% - ${drawerWidth}px)` },
          minWidth: 0,
          pt: "64px",
        }}
      >
        <Box
          sx={{
            maxWidth: 1500,
            mx: "auto",
            px: { xs: 2, sm: 3, lg: 4 },
            py: 4,
          }}
        >
          <Outlet />
        </Box>
      </Box>

      <ApplicationInfoDialog
        onClose={() => setInformationOpen(false)}
        open={informationOpen}
      />
    </Box>
  );
}
