import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Header } from "../src/components/Header";

describe("application header", () => {
  it("keeps runtime facts out of button-like header controls", () => {
    render(<Header reviewActivityAvailable={false} />);

    expect(screen.getByRole("link", { name: "ChangeSafe home" })).toBeVisible();
    expect(screen.queryByText("Snapshot replay")).not.toBeInTheDocument();
    expect(
      screen.queryByText("Preview only / snapshot mode"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Review activity" }),
    ).not.toBeInTheDocument();
  });

  it("opens the private review view only when it is available", async () => {
    const user = userEvent.setup();
    const onOpenReviewActivity = vi.fn();
    render(
      <Header
        onOpenReviewActivity={onOpenReviewActivity}
        reviewActivityAvailable
      />,
    );

    await user.click(screen.getByRole("button", { name: "Review activity" }));

    expect(onOpenReviewActivity).toHaveBeenCalledOnce();
  });
});
