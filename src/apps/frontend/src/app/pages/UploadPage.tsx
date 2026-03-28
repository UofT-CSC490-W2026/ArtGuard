import { useState, useRef, type ChangeEvent } from "react";
import { useNavigate } from "react-router";
import { useAuth } from "../contexts/AuthContext";
import { Header } from "../components/Header";
import { PageHeader } from "../components/PageHeader";
import { BrushDivider } from "../components/BrushDivider";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Alert, AlertDescription } from "../components/ui/alert";
import { getErrorMessage } from "../types";
import { analyzeArtwork } from "../api/analysis";
import { hasApiBackend } from "../api/client";
import { Upload } from "lucide-react";
import { MAX_UPLOAD_BYTES, MAX_UPLOAD_MB, hasAllowedImageExtension } from "../lib/uploadLimits";

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

    if (!hasAllowedImageExtension(file.name)) {
      setError(
        "Invalid file extension. Use JPG, JPEG, PNG, BMP, TIFF, or WEBP.",
      );
      return;
    }

    if (!file.type.startsWith("image/")) {
      setError("Invalid image format. Please upload a valid image file.");
      return;
    }

    if (file.size > MAX_UPLOAD_BYTES) {
      setError(`File too large. Please upload an image smaller than ${MAX_UPLOAD_MB}MB.`);
      return;
    }

    setSelectedFile(file);

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

      <PageHeader
        title="Upload artwork"
        description="Provide an image with artist and artwork title for patch-level authenticity analysis and RAG-grounded explanation."
        contentClassName="max-w-3xl mx-auto"
      />

      <BrushDivider />

      <main className="mx-auto max-w-2xl px-6 py-16">
        <form onSubmit={handleSubmit} className="space-y-8">
          {error && (
            <Alert variant="destructive">
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {/* Upload */}
          {!selectedFile ? (
            <div
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              className={`group cursor-pointer border border-dashed rounded-md p-16 text-center transition ${
                isDragging
                  ? "border-foreground bg-muted/30"
                  : "border-border hover:border-foreground/40"
              }`}
            >
              <Upload className="mx-auto mb-4 size-6 text-muted-foreground group-hover:text-foreground" />
              <p className="text-sm text-muted-foreground">
                Drop image or click to upload
              </p>
              <p className="mt-2 text-xs text-muted-foreground/70">
                JPG, PNG, BMP, TIFF, WEBP · max {MAX_UPLOAD_MB}MB
              </p>
            </div>
          ) : (
            <div className="flex items-center gap-4">
              <img src={preview} className="h-20 w-20 object-cover rounded" />
              <div className="flex-1 text-sm">
                <p className="truncate text-foreground">{selectedFile.name}</p>
                <p className="text-muted-foreground">
                  {(selectedFile.size / 1024 / 1024).toFixed(2)} MB
                </p>
              </div>
              <button
                type="button"
                onClick={handleRemoveFile}
                className="text-muted-foreground hover:text-foreground"
              >
                Remove
              </button>
            </div>
          )}

          <input
            ref={fileInputRef}
            type="file"
            accept="image/*"
            onChange={handleFileInput}
            className="hidden"
          />

          {/* Inputs */}
          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <div>
              <label className="block text-xs text-muted-foreground mb-2">
                Artist
              </label>
              <Input
                value={artistName}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setArtistName(e.target.value)}
                placeholder="Rembrandt van Rijn"
                disabled={isUploading}
              />
            </div>

            <div>
              <label className="block text-xs text-muted-foreground mb-2">
                Title
              </label>
              <Input
                value={artworkName}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setArtworkName(e.target.value)}
                placeholder="The Night Watch"
                disabled={isUploading}
              />
            </div>
          </div>

          {/* Button */}
          <Button
            type="submit"
            className="w-full"
            disabled={!isFormValid || isUploading}
          >
            {isUploading ? "Analyzing…" : "Analyze artwork"}
          </Button>
        </form>
      </main>
    </div>
  );
}