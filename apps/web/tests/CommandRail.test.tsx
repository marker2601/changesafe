import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CommandRail } from "../src/components/CommandRail";
import { passedWarehouseValidation } from "./fixtures";

describe("CommandRail", () => {
  it("links every completed safety gate to inspectable evidence", () => {
    render(
      <CommandRail
        artifactCount={7}
        passedChecks={12}
        runState="awaiting_approval"
        totalChecks={12}
      />,
    );

    expect(screen.getByRole("link", { name: /Observe/ })).toHaveAttribute(
      "href",
      "#dependency-heading",
    );
    expect(screen.getByRole("link", { name: /Understand/ })).toHaveAttribute(
      "href",
      "#impact-heading",
    );
    expect(screen.getByRole("link", { name: /Prepare/ })).toHaveAttribute(
      "href",
      "#artifacts",
    );
    expect(screen.getByRole("link", { name: /Prove/ })).toHaveAttribute(
      "href",
      "#validation",
    );
    expect(screen.getByRole("link", { name: /Authorize/ })).toHaveAttribute(
      "href",
      "#approval",
    );
  });

  it("keeps static checks separate from warehouse evidence", () => {
    render(
      <CommandRail
        artifactCount={7}
        passedChecks={12}
        runState="awaiting_approval"
        totalChecks={12}
        contextMode="live"
        warehouseValidation={passedWarehouseValidation}
      />,
    );

    const prove = screen.getByRole("link", { name: /Prove/ });
    expect(prove).toHaveTextContent("12 / 12 static checks");
    expect(prove).toHaveTextContent("Warehouse: passed");
    expect(prove).not.toHaveTextContent("13 / 13");
  });

  it("does not badge snapshot-carried aggregate evidence as passed", () => {
    render(
      <CommandRail
        artifactCount={7}
        contextMode="snapshot"
        passedChecks={12}
        runState="awaiting_approval"
        totalChecks={12}
        warehouseValidation={passedWarehouseValidation}
      />,
    );

    const prove = screen.getByRole("link", { name: /Prove/ });
    expect(prove).toHaveTextContent("Warehouse: inconclusive");
    expect(prove).not.toHaveTextContent("Warehouse: passed");
  });
});
