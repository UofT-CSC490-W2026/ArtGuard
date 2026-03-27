import { Link } from "react-router";
import { useAuth } from "../contexts/AuthContext";
import { Button } from "./ui/button";
import { User, LogOut, UserCircle } from "lucide-react";
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

const navLink =
  "font-sans text-sm text-muted-foreground transition-colors hover:text-foreground";

export function Header({ showAuthLinks = false, authLinkText, authLinkTo }: HeaderProps) {
  const { user, isAuthenticated, logout } = useAuth();

  return (
    <header className="border-b border-border bg-background">
      <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-6">
        <Link to="/" className="font-serif text-xl font-normal tracking-tight text-foreground">
          ArtGuard
        </Link>

        <div className="flex items-center gap-6 md:gap-8">
          {showAuthLinks && authLinkText && authLinkTo && (
            <Link to={authLinkTo} className={navLink}>
              {authLinkText}
            </Link>
          )}

          {isAuthenticated && user && (
            <>
              <nav className="flex flex-wrap items-center justify-end gap-x-5 gap-y-2">
                <Link to="/upload" className={navLink}>
                  Upload
                </Link>
                <Link to="/history" className={navLink}>
                  History
                </Link>
              </nav>

              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" className="h-auto rounded-none px-0 font-sans text-sm text-muted-foreground hover:bg-transparent hover:text-foreground">
                    <User className="size-4 mr-2 opacity-60" />
                    {user.username}
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="rounded-none border-border">
                  <DropdownMenuItem asChild>
                    <Link to="/profile" className="cursor-pointer font-sans">
                      <UserCircle className="size-4 mr-2 opacity-60" />
                      Profile
                    </Link>
                  </DropdownMenuItem>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem onClick={logout} className="font-sans">
                    <LogOut className="size-4 mr-2 opacity-60" />
                    Log out
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
