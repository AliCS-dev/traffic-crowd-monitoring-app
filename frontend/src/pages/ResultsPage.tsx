import { useState, type FormEvent } from "react";
import { Box, Button, TextField } from "@mui/material";
import { Search } from "lucide-react";
import { useNavigate, useParams } from "react-router-dom";

import { PageHeader } from "../components/PageHeader.tsx";
import { StatePanel } from "../components/StatePanel.tsx";

export function ResultsPage() {
  const { sessionId } = useParams();
  const navigate = useNavigate();
  const [lookupValue, setLookupValue] = useState(sessionId ?? "");
  const [lookupError, setLookupError] = useState(false);
  const numericSessionId = sessionId === undefined ? null : Number(sessionId);
  const invalidSessionId =
    numericSessionId !== null &&
    (!Number.isInteger(numericSessionId) || numericSessionId < 1);

  function handleLookup(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedValue = lookupValue.trim();
    if (!/^[1-9]\d*$/.test(normalizedValue)) {
      setLookupError(true);
      return;
    }
    setLookupError(false);
    navigate(`/analyses/${Number(normalizedValue)}`);
  }

  return (
    <>
      <PageHeader
        description="Inspect visual output, counts, grid summaries, and experimental alerts."
        title="Analysis results"
      />
      <Box
        component="form"
        onSubmit={handleLookup}
        sx={{
          display: "flex",
          alignItems: "flex-start",
          gap: 1.5,
          mb: 3,
          maxWidth: 430,
        }}
      >
        <TextField
          error={lookupError}
          fullWidth
          helperText={lookupError ? "Enter a positive session ID." : " "}
          label="Session ID"
          onChange={(event) => setLookupValue(event.target.value)}
          size="small"
          slotProps={{ htmlInput: { inputMode: "numeric" } }}
          value={lookupValue}
        />
        <Button
          startIcon={<Search aria-hidden size={18} />}
          sx={{ minHeight: 40 }}
          type="submit"
          variant="contained"
        >
          Find
        </Button>
      </Box>
      {invalidSessionId ? (
        <StatePanel
          description="The session identifier must be a positive integer."
          kind="error"
          title="Invalid analysis reference"
        />
      ) : (
        <StatePanel
          description={
            numericSessionId === null
              ? "Choose a monitoring session to inspect its analysis."
              : `No result has been loaded for session ${numericSessionId}.`
          }
          kind="empty"
          title={
            numericSessionId === null
              ? "No analysis selected"
              : `Analysis ${numericSessionId}`
          }
        />
      )}
    </>
  );
}
