import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import App from "../App";

describe("Clinical Command Center privacy mode", () => {
  it("shows patient names and Privacy Off when the dashboard first loads", () => {
    render(<App />);

    expect(screen.getByText("PharmaAide")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Triage Queue", level: 1 })).toBeTruthy();
    expect(screen.queryByText("Command Center")).not.toBeInTheDocument();
    expect(screen.queryByText("Privacy Off")).not.toBeInTheDocument();
    expect(screen.queryByText("Privacy Active")).not.toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Privacy Mode" })).not.toBeChecked();
    expect(screen.getByText("Mary Silva")).toBeTruthy();
    expect(screen.getByText("Jonah Davis")).toBeTruthy();
    expect(screen.queryByText("Initiate Outreach")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Initiate Outreach" })).toHaveLength(2);
  });

  it("masks patient names and shows Privacy Active after privacy mode is enabled", async () => {
    const user = userEvent.setup();
    render(<App />);

    const privacySwitch = screen.getByRole("switch", { name: "Privacy Mode" });

    await user.click(privacySwitch);

    expect(screen.queryByText("Privacy Off")).not.toBeInTheDocument();
    expect(screen.queryByText("Privacy Active")).not.toBeInTheDocument();
    expect(privacySwitch).toBeChecked();
    expect(screen.getByText("M*** S***")).toBeTruthy();
    expect(screen.getByText("J*** D***")).toBeTruthy();
    expect(screen.queryByText("Mary Silva")).toBeNull();
    expect(screen.queryByText("Jonah Davis")).toBeNull();
  });
});
