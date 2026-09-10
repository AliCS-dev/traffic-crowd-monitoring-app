import { useQueryClient } from "@tanstack/react-query";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, it, vi } from "vitest";
import { renderApplication } from "../test/render.tsx";
import { BackendStatus } from "./BackendStatus.tsx";

function RefreshHealth() {
  const client = useQueryClient();
  return (
    <button
      onClick={() =>
        client.invalidateQueries({ queryKey: ["service", "health"] })
      }
    >
      Refresh health
    </button>
  );
}

it("marks cached health as unavailable after a failed refresh and recovers", async () => {
  const user = userEvent.setup();
  const healthy = () =>
    new Response(
      JSON.stringify({ status: "ok", service: "test", version: "0.1.0" }),
      { status: 200, headers: { "content-type": "application/json" } },
    );
  vi.stubGlobal(
    "fetch",
    vi
      .fn()
      .mockResolvedValueOnce(healthy())
      .mockRejectedValueOnce(new TypeError("Offline"))
      .mockResolvedValueOnce(healthy()),
  );
  renderApplication(
    <>
      <BackendStatus />
      <RefreshHealth />
    </>,
  );
  expect(await screen.findByText("Backend online")).toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Refresh health" }));
  expect(await screen.findByText("Backend unavailable")).toBeInTheDocument();
  expect(screen.queryByText("Backend online")).not.toBeInTheDocument();
  await user.click(screen.getByRole("button", { name: "Refresh health" }));
  expect(await screen.findByText("Backend online")).toBeInTheDocument();
});
