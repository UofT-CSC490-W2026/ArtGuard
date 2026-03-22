import { useState, useEffect } from "react";
import { useAuth } from "../contexts/AuthContext";
import { hasApiBackend, api } from "../api/client";
import { Header } from "../components/Header";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Separator } from "../components/ui/separator";
import { getErrorMessage } from "../types";
import { User, Mail, Lock, Save } from "lucide-react";
import { toast } from "sonner";

export function ProfilePage() {
  const { user, updateProfile, changePassword } = useAuth();
  
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  
  const [isUpdatingProfile, setIsUpdatingProfile] = useState(false);
  const [isChangingPassword, setIsChangingPassword] = useState(false);
  
  const [profileError, setProfileError] = useState("");
  const [passwordError, setPasswordError] = useState("");
  /** null = loading or stats unavailable; number = count from API or local history */
  const [totalAnalyses, setTotalAnalyses] = useState<number | null>(null);

  useEffect(() => {
    if (user) {
      setUsername(user.username);
      setEmail(user.email);
    }
  }, [user]);

  useEffect(() => {
    if (!user?.id) return;
    if (!hasApiBackend()) {
      try {
        const n = JSON.parse(
          localStorage.getItem(`artguard_history_${user.id}`) || "[]"
        ).length;
        setTotalAnalyses(typeof n === "number" ? n : 0);
      } catch {
        setTotalAnalyses(0);
      }
      return;
    }
    let cancelled = false;
    api
      .get<{ count: number }>("/inferences/stats")
      .then((r) => {
        if (!cancelled) setTotalAnalyses(r.count);
      })
      .catch(() => {
        if (!cancelled) setTotalAnalyses(null);
      });
    return () => {
      cancelled = true;
    };
  }, [user?.id]);

  const handleUpdateProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileError("");

    if (username.length < 3) {
      setProfileError("Username must be at least 3 characters");
      return;
    }

    if (!email.includes("@")) {
      setProfileError("Invalid email format");
      return;
    }

    setIsUpdatingProfile(true);

    try {
      await updateProfile(username, email);
      toast.success("Profile updated successfully!");
    } catch (err) {
      setProfileError(getErrorMessage(err));
    } finally {
      setIsUpdatingProfile(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError("");

    if (!currentPassword) {
      setPasswordError("Please enter your current password");
      return;
    }

    if (newPassword.length < 6) {
      setPasswordError("New password must be at least 6 characters");
      return;
    }

    if (newPassword !== confirmPassword) {
      setPasswordError("New passwords do not match");
      return;
    }

    setIsChangingPassword(true);

    try {
      await changePassword(currentPassword, newPassword);
      toast.success("Password changed successfully!");
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (err) {
      setPasswordError(getErrorMessage(err));
    } finally {
      setIsChangingPassword(false);
    }
  };

  const profileChanged = username !== user?.username || email !== user?.email;

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="container mx-auto px-4 py-8">
        <div className="max-w-2xl mx-auto">
          <div className="mb-8">
            <h1 className="text-3xl mb-2">Profile Settings</h1>
            <p className="text-gray-600">
              Manage your account information and security
            </p>
          </div>

          <div className="space-y-6">
            {/* Profile Information */}
            <Card>
              <CardHeader>
                <CardTitle>Profile Information</CardTitle>
                <CardDescription>
                  Update your username and email address
                </CardDescription>
              </CardHeader>
              <CardContent>
                {profileError && (
                  <Alert variant="destructive" className="mb-6">
                    <AlertDescription>{profileError}</AlertDescription>
                  </Alert>
                )}

                <form onSubmit={handleUpdateProfile} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="username">
                      <User className="size-4 inline mr-2" />
                      Username
                    </Label>
                    <Input
                      id="username"
                      type="text"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                      disabled={isUpdatingProfile}
                      placeholder="Enter username"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="email">
                      <Mail className="size-4 inline mr-2" />
                      Email Address
                    </Label>
                    <Input
                      id="email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      disabled={isUpdatingProfile}
                      placeholder="Enter email"
                    />
                  </div>

                  <Button
                    type="submit"
                    disabled={!profileChanged || isUpdatingProfile}
                    className="w-full"
                  >
                    <Save className="size-4 mr-2" />
                    {isUpdatingProfile ? "Saving..." : "Save Changes"}
                  </Button>
                </form>
              </CardContent>
            </Card>

            {/* Account Stats */}
            <Card>
              <CardHeader>
                <CardTitle>Account Statistics</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="space-y-3">
                  <div className="flex justify-between items-center">
                    <span className="text-gray-600">Account ID</span>
                    <span className="font-mono text-sm">{user?.id}</span>
                  </div>
                  <Separator />
                  <div className="flex justify-between items-center">
                    <span className="text-gray-600">Total Analyses</span>
                    <span className="font-semibold">
                      {totalAnalyses === null ? "—" : totalAnalyses}
                    </span>
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* Change Password */}
            <Card>
              <CardHeader>
                <CardTitle>Change Password</CardTitle>
                <CardDescription>
                  Update your password to keep your account secure
                </CardDescription>
              </CardHeader>
              <CardContent>
                {passwordError && (
                  <Alert variant="destructive" className="mb-6">
                    <AlertDescription>{passwordError}</AlertDescription>
                  </Alert>
                )}

                <form onSubmit={handleChangePassword} className="space-y-4">
                  <div className="space-y-2">
                    <Label htmlFor="currentPassword">
                      <Lock className="size-4 inline mr-2" />
                      Current Password
                    </Label>
                    <Input
                      id="currentPassword"
                      type="password"
                      value={currentPassword}
                      onChange={(e) => setCurrentPassword(e.target.value)}
                      disabled={isChangingPassword}
                      placeholder="Enter current password"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="newPassword">New Password</Label>
                    <Input
                      id="newPassword"
                      type="password"
                      value={newPassword}
                      onChange={(e) => setNewPassword(e.target.value)}
                      disabled={isChangingPassword}
                      placeholder="Enter new password (min 6 characters)"
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="confirmPassword">Confirm New Password</Label>
                    <Input
                      id="confirmPassword"
                      type="password"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      disabled={isChangingPassword}
                      placeholder="Confirm new password"
                    />
                  </div>

                  <Button
                    type="submit"
                    disabled={isChangingPassword}
                    className="w-full"
                  >
                    <Lock className="size-4 mr-2" />
                    {isChangingPassword ? "Changing Password..." : "Change Password"}
                  </Button>
                </form>
              </CardContent>
            </Card>
          </div>
        </div>
      </main>
    </div>
  );
}
