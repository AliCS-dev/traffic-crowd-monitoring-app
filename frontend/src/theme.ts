import { createTheme } from "@mui/material/styles";

export const appTheme = createTheme({
  palette: {
    mode: "light",
    primary: {
      main: "#176b61",
      dark: "#0f4f48",
      light: "#dcefeb",
      contrastText: "#ffffff",
    },
    secondary: {
      main: "#315b85",
    },
    warning: {
      main: "#b26a00",
    },
    error: {
      main: "#b42318",
    },
    background: {
      default: "#f5f7f8",
      paper: "#ffffff",
    },
    text: {
      primary: "#17222b",
      secondary: "#586773",
    },
    divider: "#d8dfe3",
  },
  shape: {
    borderRadius: 6,
  },
  typography: {
    fontFamily:
      'Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
    h1: {
      fontSize: "1.75rem",
      fontWeight: 700,
      lineHeight: 1.25,
    },
    h2: {
      fontSize: "1.125rem",
      fontWeight: 700,
      lineHeight: 1.35,
    },
    button: {
      fontWeight: 650,
      letterSpacing: 0,
      textTransform: "none",
    },
    body1: {
      letterSpacing: 0,
    },
    body2: {
      letterSpacing: 0,
    },
  },
  components: {
    MuiButtonBase: {
      defaultProps: {
        disableRipple: true,
      },
    },
    MuiButton: {
      defaultProps: {
        disableElevation: true,
      },
    },
    MuiPaper: {
      defaultProps: {
        elevation: 0,
      },
    },
  },
});
