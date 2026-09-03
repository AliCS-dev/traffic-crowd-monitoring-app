import { Box, Typography } from "@mui/material";

interface PageHeaderProps {
  title: string;
  description: string;
}

export function PageHeader({ title, description }: PageHeaderProps) {
  return (
    <Box component="header" sx={{ mb: { xs: 3, md: 4 } }}>
      <Typography component="h1" variant="h1">
        {title}
      </Typography>
      <Typography color="text.secondary" sx={{ mt: 0.75, maxWidth: 720 }}>
        {description}
      </Typography>
    </Box>
  );
}
