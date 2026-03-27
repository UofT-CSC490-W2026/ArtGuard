import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PageHeader } from "./PageHeader";

describe("PageHeader", () => {
  it("renders title, optional description and actions", () => {
    render(
      <PageHeader
        title="T"
        description="D"
        actions={<button type="button">Act</button>}
      />,
    );
    expect(screen.getByRole("heading", { name: "T" })).toBeInTheDocument();
    expect(screen.getByText("D")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Act" })).toBeInTheDocument();
  });

  it("omits description and actions when absent", () => {
    render(<PageHeader title="Only" />);
    expect(screen.queryByText("D")).not.toBeInTheDocument();
  });
});
