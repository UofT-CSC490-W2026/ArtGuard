import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { AuthProvider } from "../contexts/AuthContext";
import { SignUpPage } from "./SignUpPage";

function getFormSignUpButton(): HTMLElement {
  const form = document.querySelector("form");
  if (!form) throw new Error("expected signup form");
  const btn = within(form).getByRole("button", { name: /^sign up$/i });
  return btn;
}

describe("SignUpPage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("shows success after valid signup in mock mode", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={["/signup"]}>
        <AuthProvider>
          <Routes>
            <Route path="/signup" element={<SignUpPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText(/^username$/i), "newuser");
    await user.type(screen.getByLabelText(/^email$/i), "newuser@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "password1");
    await user.click(getFormSignUpButton());

    await waitFor(() => {
      expect(
        screen.getByText(/account created successfully/i),
      ).toBeInTheDocument();
    });
  });

  it("shows error when email is already registered", async () => {
    const user = userEvent.setup();
    localStorage.setItem(
      "artguard_users",
      JSON.stringify([
        {
          id: "x",
          username: "taken",
          email: "taken@example.com",
          passwordHash: "x",
        },
      ]),
    );

    render(
      <MemoryRouter initialEntries={["/signup"]}>
        <AuthProvider>
          <Routes>
            <Route path="/signup" element={<SignUpPage />} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText(/^username$/i), "other");
    await user.type(screen.getByLabelText(/^email$/i), "taken@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "password1");
    await user.click(getFormSignUpButton());

    await waitFor(() => {
      expect(screen.getByText(/email already registered/i)).toBeInTheDocument();
    });
  });
});
