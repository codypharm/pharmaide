import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import App from "../App";

describe("Clinical Command Center privacy mode", () => {
  it("shows patient names and Privacy Off when the dashboard first loads", () => {
    render(<App />);

    expect(screen.getByText("PharmaAide")).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Triage Queue", level: 1 })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Triage Queue" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Patient Surveillance" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Adherence Heatmaps" })).toBeTruthy();
    expect(screen.queryByText("Command Center")).not.toBeInTheDocument();
    expect(screen.queryByText("Privacy Off")).not.toBeInTheDocument();
    expect(screen.queryByText("Privacy Active")).not.toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Privacy Mode" })).not.toBeChecked();
    expect(screen.getByText("System Health")).toBeTruthy();
    expect(screen.getByText("Quick Triage Actions")).toBeTruthy();
    expect(screen.getByText("Recent Interventions")).toBeTruthy();
    expect(screen.getByText(/System Alert:/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Filter recent interventions" })).toBeTruthy();
    expect(screen.getByText("Mary Silva")).toBeTruthy();
    expect(screen.getByText("Jonah Davis")).toBeTruthy();
    expect(screen.queryByText("Initiate Outreach")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Initiate Outreach" })).toHaveLength(3);
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

  it("filters critical escalations by warning severity", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Filter critical escalations" }));
    await user.click(screen.getByRole("menuitemradio", { name: "Warning" }));

    expect(screen.getByText("Potential Interaction Flag")).toBeTruthy();
    expect(screen.queryByText("Consecutive Missed Doses: Apixaban")).not.toBeInTheDocument();
    expect(screen.queryByText("Severe Symptom Report: Dyspnea")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Filter critical escalations" }));
    await user.click(screen.getByRole("menuitemradio", { name: "All" }));

    expect(screen.getByText("Consecutive Missed Doses: Apixaban")).toBeTruthy();
    expect(screen.getByText("Severe Symptom Report: Dyspnea")).toBeTruthy();
    expect(screen.getByText("Potential Interaction Flag")).toBeTruthy();
  });

  it("filters recent interventions by priority", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "Filter recent interventions" }));
    await user.click(screen.getByRole("menuitemradio", { name: "High" }));

    expect(screen.getByText("Elias Mensah")).toBeTruthy();
    expect(screen.queryByText("Rina Thomas")).not.toBeInTheDocument();
    expect(screen.queryByText("Sara Patel")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Filter recent interventions" }));
    await user.click(screen.getByRole("menuitemradio", { name: "All" }));

    expect(screen.getByText("Rina Thomas")).toBeTruthy();
    expect(screen.getByText("Elias Mensah")).toBeTruthy();
    expect(screen.getByText("Sara Patel")).toBeTruthy();
  });

  it("opens the patient surveillance roster from the sidebar", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("link", { name: "Patient Surveillance" }));

    expect(screen.getByRole("heading", { name: "Patient Surveillance", level: 1 })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Patient Directory", level: 2 })).toBeTruthy();
    expect(screen.getByText("Active surveillance roster. Last updated: 14:32 EST")).toBeTruthy();
    expect(screen.getByText("P-8834")).toBeTruthy();
    expect(screen.getByText("Thomas Jenkins")).toBeTruthy();
    expect(screen.getByText("42%")).toBeTruthy();
    expect(screen.getByText("High Risk")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Patient Surveillance" })).toHaveAttribute("aria-current", "page");
  });

  it("opens adherence heatmaps and filters the matrix by risk", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("link", { name: "Adherence Heatmaps" }));

    expect(screen.getByRole("heading", { name: "Adherence Heatmaps", level: 1 })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Population Adherence Heatmap", level: 2 })).toBeTruthy();
    expect(screen.getByText("Taken")).toBeTruthy();
    expect(screen.getByText("Missed")).toBeTruthy();
    expect(screen.getAllByText("No Data").length).toBeGreaterThan(0);
    expect(screen.getByRole("grid", { name: "Population Adherence Heatmap" })).toBeTruthy();
    expect(screen.getAllByText("PT-4410-X")).toHaveLength(2);
    expect(screen.queryByText("PT-8842-A")).not.toBeInTheDocument();
    expect(screen.getByText("Critical Alerts")).toBeTruthy();
    expect(screen.getByText("3 Actions")).toBeTruthy();
    expect(screen.getByText("7 Days Missed")).toBeTruthy();
    expect(screen.getByText("Showing 146 additional patient records below...")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Adherence Heatmaps" })).toHaveAttribute("aria-current", "page");

    await user.selectOptions(screen.getByLabelText("Risk Stratification"), "All Patients");

    expect(screen.getByText("PT-8842-A")).toBeTruthy();
    expect(screen.getByText("PT-9102-C")).toBeTruthy();
  });
});
