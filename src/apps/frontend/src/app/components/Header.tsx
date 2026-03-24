import { Link } from "react-router";
import { useAuth } from "../contexts/AuthContext";
import { Button } from "./ui/button";
import { Shield, User, LogOut, Upload, History, UserCircle, Sparkles, Terminal } from "lucide-react";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "./ui/dropdown-menu";

interface HeaderProps {
  showAuthLinks?: boolean;
  authLinkText?: string;
  authLinkTo?: string;
}

export function Header({ showAuthLinks = false, authLinkText, authLinkTo }: HeaderProps) {
  const { user, isAuthenticated, logout } = useAuth();

  return (
    <header className="border-b border-border bg-card">
      <div className="container mx-auto px-4 py-4 flex items-center justify-between">
        <Link to="/" className="flex items-center gap-2">
          <Shield className="size-7 text-accent-warm" strokeWidth={1.5} />
          <span className="font-serif text-2xl font-semibold text-foreground">ArtGuard</span>
        </Link>

        <div className="flex items-center gap-4 font-sans">
          {showAuthLinks && authLinkText && authLinkTo && (
            <Link to={authLinkTo}>
              <Button variant="ghost" className="rounded-md">{authLinkText}</Button>
            </Link>
          )}

          {isAuthenticated && user && (
            <>
              <nav className="flex items-center gap-2">
                <Button variant="ghost" asChild className="rounded-md">
                  <Link to="/upload">
                    <Upload className="size-4 mr-2" />
                    Upload
                  </Link>
                </Button>
                <Button variant="ghost" asChild className="rounded-md">
                  <Link to="/history">
                    <History className="size-4 mr-2" />
                    History
                  </Link>
                </Button>
                <Button variant="ghost" asChild className="rounded-md">
                  <Link to="/advanced">
                    <Sparkles className="size-4 mr-2" />
                    Batch Analysis
                  </Link>
                </Button>
                <Button variant="ghost" asChild className="rounded-md">
                  <Link to="/developer">
                    <Terminal className="size-4 mr-2" />
                    API tools
                  </Link>
                </Button>
              </nav>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" className="flex items-center gap-2 rounded-md border-border">
                    <User className="size-4" />
                    {user.username}
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem asChild>
                    <Link to="/profile" className="cursor-pointer">
                      <UserCircle className="size-4 mr-2" />
                      Profile Settings
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={logout}>
                    <LogOut className="size-4 mr-2" />
                    Logout
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </>
          )}
        </div>
      </div>
    </header>
  );
}