import { useState, useRef } from "react";
import { useAuth } from "../contexts/AuthContext";
import { Header } from "../components/Header";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Progress } from "../components/ui/progress";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Upload, X, FileImage, Loader2 } from "lucide-react";
import { hasApiBackend } from "../api/client";
import { analyzeArtwork } from "../api/analysis";
import { getErrorMessage, type AnalysisResult, type ScoreSemantics } from "../types";
import { getBatchIndicator } from "../lib/analysisDisplay";

interface UploadedFile {
  id: string;
  file: File;
  preview: string;
  artistName: string;
  artworkName: string;
  score?: number;
  prediction?: number;
  scoreSemantics?: ScoreSemantics;
}

export function AdvancedPage() {
  const { user } = useAuth();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [batchFiles, setBatchFiles] = useState<UploadedFile[]>([]);
  const [isAnalyzingBatch, setIsAnalyzingBatch] = useState(false);
  const [batchProgress, setBatchProgress] = useState(0);
  const [batchError, setBatchError] = useState("");

  const handleBatchFileSelect = (files: FileList) => {
    Array.from(files).forEach((file) => {
      if (file.type.startsWith("image/") && file.size <= 10 * 1024 * 1024) {
        const reader = new FileReader();
        reader.onloadend = () => {
          const uploadedFile: UploadedFile = {
            id: `${Date.now()}-${Math.random()}`,
            file,
            preview: reader.result as string,
            artistName: "",
            artworkName: file.name.replace(/\.[^/.]+$/, ""),
          };
          setBatchFiles((prev) => [...prev, uploadedFile]);
        };
        reader.readAsDataURL(file);
      }
    });
  };

  const handleBatchAnalyze = async () => {
    if (batchFiles.length === 0) return;

    setIsAnalyzingBatch(true);
    setBatchProgress(0);
    setBatchError("");

    if (hasApiBackend()) {
      try {
        for (let i = 0; i < batchFiles.length; i++) {
          const row = batchFiles[i];
          if (!row.artistName.trim() || !row.artworkName.trim()) {
            setBatchError(
              "Each image needs both artist name and artwork name (same as single upload)."
            );
            setIsAnalyzingBatch(false);
            return;
          }
          const res = await analyzeArtwork({
            file: row.file,
            artistName: row.artistName.trim(),
            artworkName: row.artworkName.trim(),
            userId: user?.id ?? "",
          });
          setBatchFiles((prev) =>
            prev.map((file, index) =>
              index === i
                ? {
                    ...file,
                    score: res.score,
                    prediction: res.prediction ?? undefined,
                    scoreSemantics: res.scoreSemantics ?? "authenticity",
                  }
                : file
            )
          );
          setBatchProgress(((i + 1) / batchFiles.length) * 100);
        }
      } catch (e) {
        setBatchError(getErrorMessage(e));
      } finally {
        setIsAnalyzingBatch(false);
      }
      return;
    }

    for (let i = 0; i < batchFiles.length; i++) {
      await new Promise((resolve) => setTimeout(resolve, 1000));
      const prediction = Math.random() > 0.5 ? 1 : 0;
      const score =
        prediction === 1 ? 0.55 + Math.random() * 0.45 : Math.random() * 0.45;
      setBatchFiles((prev) =>
        prev.map((file, index) =>
          index === i
            ? { ...file, score, prediction, scoreSemantics: "authenticity" }
            : file
        )
      );
      setBatchProgress(((i + 1) / batchFiles.length) * 100);
    }

    setIsAnalyzingBatch(false);
  };

  const removeBatchFile = (id: string) => {
    setBatchFiles((prev) => prev.filter((file) => file.id !== id));
  };

  const updateBatchFile = (id: string, field: "artistName" | "artworkName", value: string) => {
    setBatchFiles((prev) =>
      prev.map((file) =>
        file.id === id ? { ...file, [field]: value } : file
      )
    );
  };

  const indicatorForFile = (file: UploadedFile) => {
    if (file.score === undefined) return null;
    const pseudo: AnalysisResult = {
      id: file.id,
      score: file.score,
      image: "",
      artistName: file.artistName,
      artworkName: file.artworkName,
      timestamp: "",
      fileName: file.file.name,
      fileSize: file.file.size,
      prediction: file.prediction,
      scoreSemantics: file.scoreSemantics ?? "legacy_forgery",
    };
    return getBatchIndicator(pseudo, file.score);
  };

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="container mx-auto px-4 py-8">
        <div className="max-w-4xl mx-auto">
          <div className="mb-8">
            <h1 className="text-3xl mb-2">Batch Analysis</h1>
            <p className="text-gray-600">
              Upload multiple images; each row needs both artist and artwork name before analysis.
            </p>
          </div>

          <Card>
            <CardHeader>
              <CardTitle>Batch analysis</CardTitle>
              <CardDescription>
                Same inference as single upload: authenticity confidence (higher = more authentic) and model prediction when available.
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              <div>
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  multiple
                  onChange={(e) => e.target.files && handleBatchFileSelect(e.target.files)}
                  className="hidden"
                />

                <div
                  onClick={() => fileInputRef.current?.click()}
                  className="border-2 border-dashed rounded-lg p-8 text-center cursor-pointer hover:border-gray-400 transition-colors"
                >
                  <Upload className="size-12 mx-auto mb-4 text-gray-400" />
                  <p className="text-lg mb-2">Select multiple images</p>
                  <Button type="button" variant="outline">
                    <FileImage className="size-4 mr-2" />
                    Choose Files
                  </Button>
                  <p className="text-xs text-gray-500 mt-4">
                    Supported formats: JPG, PNG, GIF (max 10MB each)
                  </p>
                </div>
              </div>

              {batchFiles.length > 0 && (
                <>
                  <div className="space-y-4">
                    {batchFiles.map((file) => {
                      const indicator = indicatorForFile(file);
                      const ScoreIcon = indicator?.icon;

                      return (
                        <div key={file.id} className="border rounded-lg p-4 bg-white">
                          <div className="flex gap-4">
                            <div className="size-20 flex-shrink-0 rounded overflow-hidden bg-gray-100">
                              <img
                                src={file.preview}
                                alt={file.artworkName}
                                className="size-full object-cover"
                              />
                            </div>

                            <div className="flex-1 space-y-3">
                              <div className="flex items-start justify-between">
                                <div className="space-y-1 flex-1">
                                  <Input
                                    placeholder="Artist name (required)"
                                    value={file.artistName}
                                    onChange={(e) =>
                                      updateBatchFile(file.id, "artistName", e.target.value)
                                    }
                                    disabled={isAnalyzingBatch}
                                    className="max-w-xs"
                                    required
                                  />
                                  <Input
                                    placeholder="Artwork name (required)"
                                    value={file.artworkName}
                                    onChange={(e) =>
                                      updateBatchFile(file.id, "artworkName", e.target.value)
                                    }
                                    disabled={isAnalyzingBatch}
                                    className="max-w-xs"
                                    required
                                  />
                                </div>

                                <div className="flex items-center gap-2">
                                  {file.score !== undefined && ScoreIcon && indicator && (
                                    <div className="flex items-center gap-2">
                                      <ScoreIcon className={`size-5 ${indicator.color}`} />
                                      <span className="font-semibold">
                                        {(file.score * 100).toFixed(1)}%
                                      </span>
                                    </div>
                                  )}
                                  <Button
                                    variant="ghost"
                                    size="sm"
                                    onClick={() => removeBatchFile(file.id)}
                                    disabled={isAnalyzingBatch}
                                  >
                                    <X className="size-4" />
                                  </Button>
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>

                  {batchError && (
                    <Alert variant="destructive">
                      <AlertDescription>{batchError}</AlertDescription>
                    </Alert>
                  )}

                  {isAnalyzingBatch && (
                    <div className="space-y-2">
                      <div className="flex justify-between text-sm">
                        <span>Analyzing batch...</span>
                        <span>{Math.round(batchProgress)}%</span>
                      </div>
                      <Progress value={batchProgress} />
                    </div>
                  )}

                  <div className="flex gap-4">
                    <Button
                      onClick={handleBatchAnalyze}
                      disabled={
                        isAnalyzingBatch ||
                        batchFiles.some((f) => f.score !== undefined) ||
                        !batchFiles.every(
                          (f) => f.artistName.trim().length > 0 && f.artworkName.trim().length > 0
                        )
                      }
                      className="flex-1"
                    >
                      {isAnalyzingBatch ? (
                        <>
                          <Loader2 className="size-4 mr-2 animate-spin" />
                          Analyzing...
                        </>
                      ) : (
                        <>
                          <Upload className="size-4 mr-2" />
                          Analyze All ({batchFiles.length})
                        </>
                      )}
                    </Button>
                    {batchFiles.some(f => f.score !== undefined) && (
                      <Button
                        variant="outline"
                        onClick={() => setBatchFiles([])}
                      >
                        Clear Results
                      </Button>
                    )}
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </div>
      </main>
    </div>
  );
}
