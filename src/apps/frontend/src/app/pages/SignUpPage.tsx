import { useState } from "react";
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
import { Eye, EyeOff, CheckCircle } from "lucide-react";

const SIGNUP_ART = artAsset("rembrandt-self-portrait.jpg");

export function SignUpPage() {
  const navigate = useNavigate();
  const { signup } = useAuth();

  const [formData, setFormData] = useState({
    username: "",
    email: "",
    password: "",
  });

  const [showPassword, setShowPassword] = useState(false);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [isLoading, setIsLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrors({});
    setIsLoading(true);

    try {
      await signup(formData.username, formData.email, formData.password);
      setSuccess(true);
      setTimeout(() => {
        navigate("/login");
      }, 2000);
    } catch (err) {
      setErrors({ general: getErrorMessage(err) });
    } finally {
      setIsLoading(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
    if (errors[e.target.name]) {
      setErrors({ ...errors, [e.target.name]: "" });
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col">
      <Header showAuthLinks authLinkText="Log In" authLinkTo="/login" />

      <div className="flex flex-1 flex-col md:flex-row md:min-h-0">
        <div className="flex flex-1 items-center justify-center px-4 py-12 md:py-16 md:px-10 lg:px-16">
          <Card className="w-full max-w-md border-0 shadow-none md:border md:shadow-sm bg-transparent md:bg-card">
            <CardHeader className="space-y-1 px-0 md:px-6">
              <CardTitle className="text-2xl font-serif">Create an account</CardTitle>
              <CardDescription>
                Join ArtGuard for patch-level authenticity analysis and RAG-grounded reports.
              </CardDescription>
            </CardHeader>

            <CardContent className="px-0 md:px-6">
              {success && (
                <Alert className="mb-4 border-positive-border bg-positive-muted text-positive-foreground">
                  <CheckCircle className="size-4" />
                  <AlertDescription>
                    Account created successfully! Redirecting to login...
                  </AlertDescription>
                </Alert>
              )}

              {errors.general && (
                <Alert variant="destructive" className="mb-4">
                  <AlertDescription>{errors.general}</AlertDescription>
                </Alert>
              )}

              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="username">Username</Label>
                  <Input
                    id="username"
                    name="username"
                    type="text"
                    required
                    placeholder="Choose a username (min 3 characters)"
                    value={formData.username}
                    onChange={handleChange}
                    disabled={isLoading || success}
                  />
                  {errors.username && (
                    <p className="text-sm text-destructive">{errors.username}</p>
                  )}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    name="email"
                    type="email"
                    required
                    placeholder="Enter your email"
                    value={formData.email}
                    onChange={handleChange}
                    disabled={isLoading || success}
                  />
                  {errors.email && <p className="text-sm text-destructive">{errors.email}</p>}
                </div>

                <div className="space-y-2">
                  <Label htmlFor="password">Password</Label>
                  <div className="relative">
                    <Input
                      id="password"
                      name="password"
                      type={showPassword ? "text" : "password"}
                      required
                      placeholder="Min 6 characters"
                      value={formData.password}
                      onChange={handleChange}
                      disabled={isLoading || success}
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
                    >
                      {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
                    </button>
                  </div>
                  {errors.password && (
                    <p className="text-sm text-destructive">{errors.password}</p>
                  )}
                </div>

                <Button type="submit" className="w-full" disabled={isLoading || success}>
                  {isLoading ? "Creating account..." : "Sign up"}
                </Button>
              </form>

              <div className="mt-4 text-center text-sm">
                <span className="text-muted-foreground">Already have an account? </span>
                <Link
                  to="/login"
                  className="text-brand font-medium hover:underline underline-offset-4"
                >
                  Log in
                </Link>
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="relative hidden md:block md:w-[46%] lg:w-1/2 min-h-0">
          <img
            src={SIGNUP_ART}
            alt=""
            className="absolute inset-0 size-full object-cover"
          />
          <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/85 via-black/40 to-transparent pt-24 pb-6 px-8 text-white border-b-4 border-brand">
            <p className="font-serif text-xl font-semibold">Self-Portrait</p>
            <p className="text-sm text-white/90 mt-1">Rembrandt van Rijn · c. 1660</p>
            <p className="text-xs text-white/75 mt-1">The National Gallery, London · Public domain</p>
          </div>
        </div>
      </div>
    </div>
  );
}
