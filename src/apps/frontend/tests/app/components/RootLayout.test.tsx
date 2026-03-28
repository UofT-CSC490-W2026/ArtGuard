import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router";
import { describe, expect, it } from "vitest";
import { RootLayout } from "@/app/components/RootLayout";

describe("RootLayout", () => {
  it("renders outlet inside auth and error boundary", async () => {
    render(
      <MemoryRouter>
        <Routes>
          <Route path="/" element={<RootLayout />}>
            <Route index element={<div data-testid="out">child</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );
    expect(await screen.findByTestId("out")).toHaveTextContent("child");
  });
});
