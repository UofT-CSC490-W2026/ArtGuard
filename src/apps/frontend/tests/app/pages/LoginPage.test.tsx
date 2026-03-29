import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it } from "vitest";
import { AuthProvider } from "@/app/contexts/AuthContext";
import { LoginPage } from "@/app/pages/LoginPage";

async function seedLocalUser(
  username: string,
  email: string,
  password: string,
): Promise<void> {
  const encoder = new TextEncoder();
  const data = encoder.encode(password);
  const hash = await crypto.subtle.digest("SHA-256", data);
  const passwordHash = btoa(String.fromCharCode(...new Uint8Array(hash)));
  localStorage.setItem(
    "artguard_users",
    JSON.stringify([{ id: "u-seed", username, email, passwordHash }]),
  );
}

function renderLogin() {
  return render(
    <MemoryRouter initialEntries={["/login"]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/upload" element={<div>Upload page</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

function getLoginSubmitButton(): HTMLElement {
  const form = document.querySelector("form");
  if (!form) throw new Error("expected login form");
  const buttons = form.querySelectorAll('button[type="submit"]');
  return buttons[0] as HTMLElement;
}

describe("LoginPage", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("shows validation error for wrong password", async () => {
    const user = userEvent.setup();
    await seedLocalUser("alice", "alice@example.com", "correctpass");

    renderLogin();

    await waitFor(() => {
      const headings = screen.getAllByRole("heading", { name: /welcome back/i });
      expect(headings.length).toBeGreaterThan(0);
    });

    const emailInput = screen.getByLabelText(/^email$/i);
    const passwordInput = screen.getByLabelText(/^password$/i);
    await user.clear(emailInput);
    await user.clear(passwordInput);
    await user.type(emailInput, "alice@example.com");
    await user.type(passwordInput, "wrongpass");
    await user.click(getLoginSubmitButton());

    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert).toBeInTheDocument();
      expect(alert).toHaveTextContent("Incorrect password. Try again.");
    });
  });

  it("clears error when user types after failed login", async () => {
    const user = userEvent.setup();
    await seedLocalUser("alice", "alice@example.com", "correctpass");

    renderLogin();

    await waitFor(() => {
      expect(screen.getAllByRole("heading", { name: /welcome back/i }).length).toBeGreaterThan(0);
    });

    await user.type(screen.getByLabelText(/^email$/i), "alice@example.com");
    await user.type(screen.getByLabelText(/^password$/i), "wrongpass");
    await user.click(getLoginSubmitButton());

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });

    // Type in email field to clear the error
    await user.type(screen.getByLabelText(/^email$/i), "x");
    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    });
  });

  it("toggles password visibility", async () => {
    const user = userEvent.setup();
    renderLogin();

    await waitFor(() => {
      expect(screen.getAllByRole("heading", { name: /welcome back/i }).length).toBeGreaterThan(0);
    });

    const passwordInput = screen.getByLabelText(/^password$/i);
    expect(passwordInput).toHaveAttribute("type", "password");

    // Click the toggle button (the Eye/EyeOff button near the password field)
    const toggleBtn = passwordInput.parentElement!.querySelector("button")!;
    await user.click(toggleBtn);
    expect(passwordInput).toHaveAttribute("type", "text");

    await user.click(toggleBtn);
    expect(passwordInput).toHaveAttribute("type", "password");
  });

  it("navigates to upload after successful login", async () => {
    const user = userEvent.setup();
    await seedLocalUser("bob", "bob@example.com", "secret12");

    renderLogin();

    await waitFor(() => {
      const headings = screen.getAllByRole("heading", { name: /welcome back/i });
      expect(headings.length).toBeGreaterThan(0);
    });

    const emailInput = screen.getByLabelText(/^email$/i);
    const passwordInput = screen.getByLabelText(/^password$/i);
    await user.clear(emailInput);
    await user.clear(passwordInput);
    await user.type(emailInput, "bob@example.com");
    await user.type(passwordInput, "secret12");
    await user.click(getLoginSubmitButton());

    await waitFor(() => {
      expect(screen.getByText("Upload page")).toBeInTheDocument();
    });
  });
});
