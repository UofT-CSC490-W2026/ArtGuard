import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";

describe("App", () => {
  it("mounts router and shows home content", async () => {
    render(<App />);
    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: /shaping tomorrow's art authentication with ai/i }),
      ).toBeInTheDocument();
    });
  });
});
