import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { CommandRail } from "../src/components/CommandRail";

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
});
