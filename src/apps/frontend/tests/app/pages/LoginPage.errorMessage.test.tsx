import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";
import { LoginPage } from "@/app/pages/LoginPage";

vi.mock("@/app/contexts/AuthContext", () => ({
  useAuth: () => ({
    login: vi.fn().mockRejectedValue(new Error("Service unavailable")),
    isAuthenticated: false,
    isLoading: false,
  }),
}));

describe("LoginPage generic error handling", () => {
  it("shows raw error text when failure is not invalid-credentials", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={["/login"]}>
        <LoginPage />
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText(/^email$/i), "alice@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "secret");
    await user.click(screen.getByRole("button", { name: /log in/i }));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toHaveTextContent("Service unavailable");
    });
  });
});
