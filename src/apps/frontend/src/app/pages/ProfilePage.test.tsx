import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AuthProvider } from "../contexts/AuthContext";
import { ProfilePage } from "./ProfilePage";
import * as client from "../api/client";

function seedUser(id = "u1", username = "testuser", email = "test@example.com") {
  localStorage.setItem("artguard_user", JSON.stringify({ id, username, email }));
}

async function seedLocalUserWithHash(id: string, username: string, email: string, password: string) {
  const encoder = new TextEncoder();
  const data = encoder.encode(password);
  const hash = await crypto.subtle.digest("SHA-256", data);
  const passwordHash = btoa(String.fromCharCode(...new Uint8Array(hash)));
  localStorage.setItem("artguard_users", JSON.stringify([{ id, username, email, passwordHash }]));
}

function renderProfile() {
  return render(
    <MemoryRouter initialEntries={["/profile"]}>
      <AuthProvider>
        <Routes>
          <Route path="/profile" element={<ProfilePage />} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("ProfilePage", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
    vi.spyOn(client, "hasApiBackend").mockReturnValue(false);
  });

  it("renders profile form with user data pre-filled", async () => {
    seedUser("u1", "testuser", "test@example.com");
    renderProfile();
    await waitFor(() => expect(screen.getByDisplayValue("testuser")).toBeInTheDocument());
    expect(screen.getByDisplayValue("test@example.com")).toBeInTheDocument();
  });

  it("shows account ID in statistics section", async () => {
    seedUser("my-user-id-123");
    renderProfile();
    await waitFor(() => expect(screen.getByText("my-user-id-123")).toBeInTheDocument());
  });

  it("shows total analyses count from localStorage", async () => {
    seedUser("u1");
    const history = [{ id: "1" }, { id: "2" }, { id: "3" }];
    localStorage.setItem("artguard_history_u1", JSON.stringify(history));
    renderProfile();
    await waitFor(() => expect(screen.getByText("3")).toBeInTheDocument());
  });

  it("shows zero analyses when localStorage history is corrupt", async () => {
    seedUser("u1");
    localStorage.setItem("artguard_history_u1", "{bad-json{{");
    renderProfile();
    await waitFor(() => expect(screen.getByText("0")).toBeInTheDocument());
  });

  it("shows total analyses count from API when backend is available", async () => {
    vi.spyOn(client, "hasApiBackend").mockReturnValue(true);
    vi.spyOn(client, "getAccessToken").mockReturnValue("token");
    vi.spyOn(client.api, "get").mockImplementation(async (path: string) => {
      if (path === "/auth/me") return { id: "u1", username: "testuser", email: "test@example.com" };
      if (path === "/inferences/stats") return { count: 42 };
      throw new Error("unexpected");
    });
    seedUser("u1", "testuser", "test@example.com");
    renderProfile();
    await waitFor(() => expect(screen.getByText("42")).toBeInTheDocument());
  });

  it("shows dash when API stats fetch fails", async () => {
    vi.spyOn(client, "hasApiBackend").mockReturnValue(true);
    vi.spyOn(client, "getAccessToken").mockReturnValue("token");
    vi.spyOn(client.api, "get").mockImplementation(async (path: string) => {
      if (path === "/auth/me") return { id: "u1", username: "testuser", email: "test@example.com" };
      throw new Error("stats unavailable");
    });
    seedUser("u1", "testuser", "test@example.com");
    renderProfile();
    await waitFor(() => expect(screen.getByText("—")).toBeInTheDocument());
  });

  it("save changes button is disabled when nothing changed", async () => {
    seedUser("u1", "testuser", "test@example.com");
    renderProfile();
    await waitFor(() => expect(screen.getByDisplayValue("testuser")).toBeInTheDocument());
    const saveBtn = screen.getByRole("button", { name: /save changes/i });
    expect(saveBtn).toBeDisabled();
  });

  it("save changes button enables when username is modified", async () => {
    const user = userEvent.setup();
    seedUser("u1", "testuser", "test@example.com");
    await seedLocalUserWithHash("u1", "testuser", "test@example.com", "password123");
    renderProfile();
    await waitFor(() => expect(screen.getByDisplayValue("testuser")).toBeInTheDocument());

    const usernameInput = screen.getByDisplayValue("testuser");
    await user.clear(usernameInput);
    await user.type(usernameInput, "newusername");

    const saveBtn = screen.getByRole("button", { name: /save changes/i });
    expect(saveBtn).toBeEnabled();
  });

  it("shows error when username is too short on profile update", async () => {
    const user = userEvent.setup();
    seedUser("u1", "testuser", "test@example.com");
    await seedLocalUserWithHash("u1", "testuser", "test@example.com", "password123");
    renderProfile();
    await waitFor(() => expect(screen.getByDisplayValue("testuser")).toBeInTheDocument());

    const usernameInput = screen.getByDisplayValue("testuser");
    await user.clear(usernameInput);
    await user.type(usernameInput, "ab"); // too short

    const form = screen.getByDisplayValue("ab").closest("form");
    fireEvent.submit(form!);

    await waitFor(() =>
      expect(screen.getByText(/at least 3 characters/i)).toBeInTheDocument()
    );
  });

  it("shows error when email is invalid on profile update", async () => {
    const user = userEvent.setup();
    seedUser("u1", "testuser", "test@example.com");
    await seedLocalUserWithHash("u1", "testuser", "test@example.com", "password123");
    renderProfile();
    await waitFor(() => expect(screen.getByDisplayValue("testuser")).toBeInTheDocument());

    const emailInput = screen.getByDisplayValue("test@example.com");
    await user.clear(emailInput);
    await user.type(emailInput, "not-an-email");

    const form = emailInput.closest("form");
    fireEvent.submit(form!);

    await waitFor(() =>
      expect(screen.getByText(/invalid email/i)).toBeInTheDocument()
    );
  });

  it("shows error when new passwords do not match", async () => {
    const user = userEvent.setup();
    seedUser("u1", "testuser", "test@example.com");
    renderProfile();
    await waitFor(() => expect(screen.getByLabelText(/current password/i)).toBeInTheDocument());

    await user.type(screen.getByLabelText(/current password/i), "oldpass123");
    await user.type(screen.getByLabelText(/^new password$/i), "newpass123");
    await user.type(screen.getByLabelText(/confirm new password/i), "differentpass");

    const form = screen.getByLabelText(/confirm new password/i).closest("form");
    fireEvent.submit(form!);

    await waitFor(() =>
      expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument()
    );
  });

  it("shows error when new password is too short", async () => {
    const user = userEvent.setup();
    seedUser("u1", "testuser", "test@example.com");
    renderProfile();
    await waitFor(() => expect(screen.getByLabelText(/current password/i)).toBeInTheDocument());

    await user.type(screen.getByLabelText(/current password/i), "oldpass");
    await user.type(screen.getByLabelText(/^new password$/i), "12345"); // too short
    await user.type(screen.getByLabelText(/confirm new password/i), "12345");

    const form = screen.getByLabelText(/confirm new password/i).closest("form");
    fireEvent.submit(form!);

    await waitFor(() =>
      expect(screen.getByText(/at least 6 characters/i)).toBeInTheDocument()
    );
  });

  it("shows error when current password field is empty", async () => {
    const user = userEvent.setup();
    seedUser("u1", "testuser", "test@example.com");
    renderProfile();
    await waitFor(() => expect(screen.getByLabelText(/current password/i)).toBeInTheDocument());

    await user.type(screen.getByLabelText(/^new password$/i), "newpass123");
    await user.type(screen.getByLabelText(/confirm new password/i), "newpass123");

    const form = screen.getByLabelText(/confirm new password/i).closest("form");
    fireEvent.submit(form!);

    await waitFor(() =>
      expect(screen.getByText(/enter your current password/i)).toBeInTheDocument()
    );
  });

  it("successfully updates profile when form is submitted", async () => {
    const user = userEvent.setup();
    seedUser("u1", "testuser", "test@example.com");
    await seedLocalUserWithHash("u1", "testuser", "test@example.com", "password123");
    renderProfile();
    await waitFor(() => expect(screen.getByDisplayValue("testuser")).toBeInTheDocument());

    const usernameInput = screen.getByDisplayValue("testuser");
    await user.clear(usernameInput);
    await user.type(usernameInput, "updateduser");

    const saveBtn = screen.getByRole("button", { name: /save changes/i });
    await user.click(saveBtn);

    // After success, username should be updated
    await waitFor(() => expect(screen.getByDisplayValue("updateduser")).toBeInTheDocument());
  });

  it("shows error when updateProfile rejects", async () => {
    const user = userEvent.setup();
    seedUser("u1", "testuser", "test@example.com");
    // Store a second user with the target email so updateProfile throws "Email is already in use"
    const users = [
      { id: "u1", username: "testuser", email: "test@example.com", passwordHash: "hash1" },
      { id: "u2", username: "other", email: "taken@example.com", passwordHash: "hash2" },
    ];
    localStorage.setItem("artguard_users", JSON.stringify(users));
    renderProfile();
    await waitFor(() => expect(screen.getByDisplayValue("testuser")).toBeInTheDocument());

    const emailInput = screen.getByDisplayValue("test@example.com");
    await user.clear(emailInput);
    await user.type(emailInput, "taken@example.com");

    const saveBtn = screen.getByRole("button", { name: /save changes/i });
    await user.click(saveBtn);

    await waitFor(() =>
      expect(screen.getByText(/email is already in use/i)).toBeInTheDocument()
    );
  });

  it("shows error when changePassword rejects in form", async () => {
    const user = userEvent.setup();
    seedUser("u1", "testuser", "test@example.com");
    await seedLocalUserWithHash("u1", "testuser", "test@example.com", "correctpass");
    renderProfile();
    await waitFor(() => expect(screen.getByLabelText(/current password/i)).toBeInTheDocument());

    await user.type(screen.getByLabelText(/current password/i), "wrongpass");
    await user.type(screen.getByLabelText(/^new password$/i), "newpass123");
    await user.type(screen.getByLabelText(/confirm new password/i), "newpass123");

    const form = screen.getByLabelText(/confirm new password/i).closest("form");
    fireEvent.submit(form!);

    await waitFor(() =>
      expect(screen.getByText(/current password is incorrect/i)).toBeInTheDocument()
    );
  });

  it("successful password change clears password fields", async () => {
    const user = userEvent.setup();
    seedUser("u1", "testuser", "test@example.com");
    await seedLocalUserWithHash("u1", "testuser", "test@example.com", "oldpass123");
    renderProfile();
    await waitFor(() => expect(screen.getByLabelText(/current password/i)).toBeInTheDocument());

    await user.type(screen.getByLabelText(/current password/i), "oldpass123");
    await user.type(screen.getByLabelText(/^new password$/i), "newpass123");
    await user.type(screen.getByLabelText(/confirm new password/i), "newpass123");

    const form = screen.getByLabelText(/confirm new password/i).closest("form");
    fireEvent.submit(form!);

    await waitFor(() => {
      expect(screen.getByLabelText(/current password/i)).toHaveValue("");
    });
  });
});
