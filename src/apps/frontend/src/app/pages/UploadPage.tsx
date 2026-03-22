import { useState, useRef } from "react";
import { useNavigate } from "react-router";
import { useAuth } from "../contexts/AuthContext";
import { Header } from "../components/Header";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Alert, AlertDescription } from "../components/ui/alert";
import { getErrorMessage } from "../types";
import { analyzeArtwork } from "../api/analysis";
import { hasApiBackend } from "../api/client";
import { Upload, X, Image as ImageIcon, FileImage, Loader2 } from "lucide-react";

export function UploadPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string>("");
  const [artistName, setArtistName] = useState("");
  const [artworkName, setArtworkName] = useState("");
  const [error, setError] = useState("");
  const [isUploading, setIsUploading] = useState(false);
  const [isDragging, setIsDragging] = useState(false);

  const handleFileSelect = (file: File) => {
    setError("");

    // Validate file type
    if (!file.type.startsWith("image/")) {
      setError("Invalid image format. Please upload a valid image file.");
      return;
    }

    // Validate file size (max 10MB)
    if (file.size > 10 * 1024 * 1024) {
      setError("File too large. Please upload an image smaller than 10MB.");
      return;
    }

    setSelectedFile(file);

    // Create preview
    const reader = new FileReader();
    reader.onloadend = () => {
      setPreview(reader.result as string);
    };
    reader.readAsDataURL(file);
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      handleFileSelect(file);
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);

    const file = e.dataTransfer.files[0];
    if (file) {
      handleFileSelect(file);
    }
  };

  const handleRemoveFile = () => {
    setSelectedFile(null);
    setPreview("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");

    // Validate inputs
    if (!selectedFile) {
      setError("Please select an image file");
      return;
    }

    if (!artistName.trim() || !artworkName.trim()) {
      setError("Please enter both Artist Name and Artwork Name");
      return;
    }

    setIsUploading(true);
    try {
      const analysisResult = await analyzeArtwork({
        file: selectedFile,
        artistName: artistName.trim(),
        artworkName: artworkName.trim(),
        userId: user?.id ?? "",
      });

      if (!analysisResult.image && preview) {
        analysisResult.image = preview;
      }

      localStorage.setItem("artguard_latest_result", JSON.stringify(analysisResult));

      if (!hasApiBackend()) {
        const historyKey = `artguard_history_${user?.id}`;
        const existingHistory = JSON.parse(localStorage.getItem(historyKey) || "[]");
        existingHistory.unshift(analysisResult);
        localStorage.setItem(historyKey, JSON.stringify(existingHistory));
      }

      navigate("/results");
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsUploading(false);
    }
  };

  const isFormValid =
    Boolean(selectedFile) && Boolean(artistName.trim()) && Boolean(artworkName.trim());

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="container mx-auto px-4 py-8">
        <div className="max-w-3xl mx-auto">
          <div className="mb-8">
            <h1 className="text-3xl mb-2">Upload Artwork</h1>
            <p className="text-gray-600">
              Upload an image and enter both the artist and artwork name for analysis
            </p>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Forgery Detection Analysis</CardTitle>
              <CardDescription>
                Our AI will analyze the artwork for signs of forgery
              </CardDescription>
            </CardHeader>

            <CardContent>
              {error && (
                <Alert variant="destructive" className="mb-6">
                  <AlertDescription>{error}</AlertDescription>
                </Alert>
              )}

              <form onSubmit={handleSubmit} className="space-y-6">
                {/* Image Upload Area */}
                <div className="space-y-4">
                  <Label>Artwork Image *</Label>

                  {!selectedFile ? (
                    <div
                      onDragOver={handleDragOver}
                      onDragLeave={handleDragLeave}
                      onDrop={handleDrop}
                      onClick={() => fileInputRef.current?.click()}
                      className={`border-2 border-dashed rounded-lg p-12 text-center cursor-pointer transition-colors ${
                        isDragging
                          ? "border-blue-500 bg-blue-50"
                          : "border-gray-300 hover:border-gray-400"
                      }`}
                    >
                      <Upload className="size-12 mx-auto mb-4 text-gray-400" />
                      <p className="text-lg mb-2">
                        Drag and drop your image here
                      </p>
                      <p className="text-sm text-gray-500 mb-4">or</p>
                      <Button type="button" variant="outline">
                        <FileImage className="size-4 mr-2" />
                        Choose File
                      </Button>
                      <p className="text-xs text-gray-500 mt-4">
                        Supported formats: JPG, PNG, GIF (max 10MB)
                      </p>
                    </div>
                  ) : (
                    <div className="border rounded-lg p-4 bg-gray-50">
                      <div className="flex gap-4">
                        <div className="relative size-32 flex-shrink-0">
                          <img
                            src={preview}
                            alt="Preview"
                            className="size-full object-cover rounded"
                          />
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="flex items-start justify-between">
                            <div className="flex-1 min-w-0">
                              <p className="font-medium truncate">
                                {selectedFile.name}
                              </p>
                              <p className="text-sm text-gray-500">
                                {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                              </p>
                              <p className="text-sm text-gray-500">
                                {selectedFile.type}
                              </p>
                            </div>
                            <Button
                              type="button"
                              variant="ghost"
                              size="sm"
                              onClick={handleRemoveFile}
                              className="ml-2"
                            >
                              <X className="size-4" />
                            </Button>
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/*"
                    onChange={handleFileInput}
                    className="hidden"
                  />
                </div>

                {/* Metadata Form */}
                <div className="space-y-4 pt-4 border-t">
                  <div className="space-y-2">
                    <Label htmlFor="artistName">Artist Name *</Label>
                    <Input
                      id="artistName"
                      type="text"
                      placeholder="e.g., Leonardo da Vinci"
                      value={artistName}
                      onChange={(e) => setArtistName(e.target.value)}
                      disabled={isUploading}
                      required
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="artworkName">Artwork Name *</Label>
                    <Input
                      id="artworkName"
                      type="text"
                      placeholder="e.g., Mona Lisa"
                      value={artworkName}
                      onChange={(e) => setArtworkName(e.target.value)}
                      disabled={isUploading}
                      required
                    />
                  </div>

                  <Alert>
                    <ImageIcon className="size-4" />
                    <AlertDescription>
                      Both artist name and artwork name are required before you can analyze.
                    </AlertDescription>
                  </Alert>
                </div>

                {/* Submit Button */}
                <Button
                  type="submit"
                  className="w-full"
                  disabled={!isFormValid || isUploading}
                  size="lg"
                >
                  {isUploading ? (
                    <>
                      <Loader2 className="size-4 mr-2 animate-spin" />
                      Analyzing Artwork...
                    </>
                  ) : (
                    "Analyze Artwork"
                  )}
                </Button>
              </form>
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}