import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Typography,
} from "@mui/material";

interface ApplicationInfoDialogProps {
  open: boolean;
  onClose: () => void;
}

export function ApplicationInfoDialog({
  open,
  onClose,
}: ApplicationInfoDialogProps) {
  return (
    <Dialog fullWidth maxWidth="xs" onClose={onClose} open={open}>
      <DialogTitle>Traffic &amp; Crowd Monitor</DialogTitle>
      <DialogContent>
        <Typography color="text.secondary">
          Aerial image and video analysis workspace for structured traffic and
          crowd monitoring results.
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  );
}
