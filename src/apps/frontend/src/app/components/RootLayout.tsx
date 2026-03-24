import { Outlet } from "react-router";
import { AuthProvider } from "../contexts/AuthContext";
import { ErrorBoundary } from "./ErrorBoundary";
import { Toaster } from "./ui/sonner";

export function RootLayout() {
  return (
    <ErrorBoundary>
      <AuthProvider>
        <div className="min-h-screen bg-background">
          <Outlet />
        </div>
        <Toaster />
      </AuthProvider>
    </ErrorBoundary>
  );
}