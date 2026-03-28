import { useState, useEffect } from "react";
import { Link, useNavigate } from "react-router";
import { useAuth } from "../contexts/AuthContext";
import { Header } from "../components/Header";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Alert, AlertDescription } from "../components/ui/alert";
import { getErrorMessage } from "../types";
import { artAsset } from "../lib/artAssets";
import { Eye, EyeOff, Loader2 } from "lucide-react";

const LOGIN_ART = artAsset("girl-with-pearl-earring.jpg");

export function LoginPage() {
  const navigate = useNavigate();
  const { login, isAuthenticated, isLoading: authLoading } = useAuth();

  const [formData, setFormData] = useState({
    email: "",
    password: "",
  });

  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  useEffect(() => {
    if (isAuthenticated) {
      navigate("/upload");
    }
  }, [isAuthenticated, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setIsLoading(true);

    try {
      await login(formData.email, formData.password);
      navigate("/upload");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
    if (error) setError("");
  };

  if (authLoading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="size-8 animate-spin text-brand" aria-hidden />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Header showAuthLinks authLinkText="Sign Up" authLinkTo="/signup" />

      <div className="flex flex-1 flex-col md:flex-row md:min-h-0">
        <div className="flex flex-1 items-center justify-center px-4 py-12 md:py-16 md:px-10 lg:px-16">
          <Card className="w-full max-w-md border-0 shadow-none md:border md:shadow-sm bg-transparent md:bg-card">
            <CardHeader className="space-y-1 px-0 md:px-6">
              <CardTitle className="text-2xl font-serif">Welcome back</CardTitle>
              <CardDescription>Sign in to run patch-level analyses and view history.</CardDescription>
            </CardHeader>

            <CardContent className="px-0 md:px-6">
              {error && (
                <Alert variant="destructive" className="mb-4">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    name="email"
                    type="email"
                    required
                    autoFocus
                    placeholder="Enter your email"
                    value={formData.email}
                    onChange={handleChange}
                    disabled={isLoading}
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="password">Password</Label>
                  <div className="relative">
                    <Input
                      id="password"
                      name="password"
                      type={showPassword ? "text" : "password"}
                      required
                      placeholder="Enter your password"
                      value={formData.password}
                      onChange={handleChange}
                      disabled={isLoading}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    >
                      {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                    </button>
                  </div>
                </div>

                <Button type="submit" className="w-full" disabled={isLoading}>
                  {isLoading ? "Logging in..." : "Log in"}
                </Button>
              </form>

              <div className="mt-4 text-center text-sm">
                <span className="text-muted-foreground">Don&apos;t have an account? </span>
                <Link
                  to="/signup"
                  className="text-brand font-medium hover:underline underline-offset-4"
                >
                  Sign up
                </Link>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="relative hidden md:block md:w-[46%] lg:w-1/2 min-h-[280px] md:min-h-0">
          <img
            src={LOGIN_ART}
            alt=""
            className="absolute inset-0 size-full object-cover"
          />
          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/40 to-transparent pt-24 pb-6 px-8 text-white border-b-4 border-brand">
            <p className="font-serif text-xl font-semibold">Girl with a Pearl Earring</p>
            <p className="text-sm text-white/90 mt-1">Johannes Vermeer · c. 1665</p>
            <p className="text-xs text-white/75 mt-1">Mauritshuis, The Hague · Public domain</p>
          </div>
        </div>
      </div>
    </div>
  );
}
