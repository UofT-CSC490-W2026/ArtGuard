import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router";
import { Header } from "../components/Header";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Progress } from "../components/ui/progress";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Separator } from "../components/ui/separator";
import {
  Upload,
  AlertCircle,
  CheckCircle,
  AlertTriangle,
  Loader2,
  Calendar,
  User,
  FileImage,
  Share2,
  Download,
} from "lucide-react";
import { toast } from "sonner";
import type { AnalysisResult } from "../types";
import {
  formatAnalysisScorePercent,
  generateFallbackExplanation,
  getAnalysisBarColor,
  getAnalysisVerdict,
  isInferenceFailed,
  primaryScoreDescription,
  primaryScoreTitle,
  usesAuthenticitySemantics,
} from "../lib/analysisDisplay";

export function ResultsPage() {
  const navigate = useNavigate();
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [explanation, setExplanation] = useState("");
  const [isLoadingExplanation, setIsLoadingExplanation] = useState(true);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const storedResult = localStorage.getItem("artguard_latest_result");
    if (!storedResult) {
      navigate("/upload");
      return;
    }
    try {
      const parsedResult = JSON.parse(storedResult) as AnalysisResult;
      if (typeof parsedResult?.score !== "number" || !parsedResult?.timestamp) {
        navigate("/upload");
        return;
      }
      setResult(parsedResult);
      if (isInferenceFailed(parsedResult)) {
        setExplanation(generateFallbackExplanation(parsedResult));
        setIsLoadingExplanation(false);
      } else {
        const backendExplanation =
          typeof parsedResult.explanation === "string" && parsedResult.explanation.trim().length > 0
            ? parsedResult.explanation.trim()
            : null;
        if (backendExplanation) {
          setExplanation(backendExplanation);
          setIsLoadingExplanation(false);
        } else {
          setTimeout(() => {
            setExplanation(generateFallbackExplanation(parsedResult));
            setIsLoadingExplanation(false);
          }, 1500);
        }
      }
    } catch {
      navigate("/upload");
    } finally {
      setIsLoading(false);
    }
  }, [navigate]);

  if (isLoading || !result) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="size-8 animate-spin text-accent-warm" aria-hidden />
      </div>
    );
  }

  const verdict = getAnalysisVerdict(result);
  const VerdictIcon = verdict.icon;
  const scorePercentage = formatAnalysisScorePercent(result);
  const predLabel =
    !isInferenceFailed(result) &&
    usesAuthenticitySemantics(result) &&
    typeof result.prediction === "number"
      ? result.prediction === 1
        ? "Authentic"
        : result.prediction === 0
          ? "Forgery"
          : "Pending"
      : null;

  const handleShare = async () => {
    const scoreLine = usesAuthenticitySemantics(result)
      ? `Authenticity confidence: ${scorePercentage}%`
      : `Score: ${scorePercentage}%`;
    const predLine = predLabel ? `Model prediction: ${predLabel}\n` : "";
    const shareText = `ArtGuard Analysis Results\n\nArtwork: ${result.artworkName}\nArtist: ${result.artistName}\n${scoreLine}\n${predLine}Verdict: ${verdict.text}`;

    if (navigator.share) {
      try {
        await navigator.share({
          title: "ArtGuard Analysis",
          text: shareText,
        });
      } catch (error) {
        // User cancelled or share failed
      }
    } else {
      // Fallback: copy to clipboard
      navigator.clipboard.writeText(shareText);
      toast.success("Results copied to clipboard!");
    }
  };

  const handleDownloadReport = () => {
    const reportContent = `
ArtGuard Forgery Detection Report
================================

Artwork Details:
- Name: ${result.artworkName}
- Artist: ${result.artistName}
- File: ${result.fileName}
- Analyzed: ${new Date(result.timestamp).toLocaleString()}

Analysis Results:
- ${usesAuthenticitySemantics(result) ? `Authenticity confidence: ${scorePercentage}%` : `Score: ${scorePercentage}%`}
${predLabel ? `- Model prediction: ${predLabel}\n` : ""}- Verdict: ${verdict.text}

Explanation:
${explanation}

Note: This analysis is AI-generated and should not be considered as a definitive authentication. 
Always consult certified art experts for professional verification.
    `.trim();

    const blob = new Blob([reportContent], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `artguard-report-${result.artworkName}-${Date.now()}.txt`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success("Report downloaded!");
  };

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="container mx-auto px-4 py-8">
        <div className="max-w-5xl mx-auto">
          <div className="mb-8">
            <h1 className="text-3xl mb-2">Analysis Results</h1>
            <p className="text-gray-600">
              {usesAuthenticitySemantics(result)
                ? "Authenticity confidence and model prediction from patch-level inference"
                : "Analysis using a legacy score scale (older saved result)"}
            </p>
          </div>

          <div className="grid lg:grid-cols-3 gap-6">
            {/* Left Column - Image and Metadata */}
            <div className="lg:col-span-1 space-y-6">
              <Card>
                <CardHeader>
                  <CardTitle>Artwork Details</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="aspect-square w-full overflow-hidden rounded-lg bg-gray-100">
                    {result.image ? (
                      <img
                        src={result.image}
                        alt="Analyzed artwork"
                        className="size-full object-cover"
                      />
                    ) : (
                      <div className="size-full flex items-center justify-center text-sm text-muted-foreground p-4 text-center">
                        Image preview unavailable (open history to refresh a signed URL).
                      </div>
                    )}
                  </div>

                  <div className="space-y-3 text-sm">
                    <div className="flex items-start gap-2">
                      <User className="size-4 mt-0.5 text-gray-500 flex-shrink-0" />
                      <div>
                        <p className="text-gray-500">Artist</p>
                        <p className="font-medium">{result.artistName}</p>
                      </div>
                    </div>

                    <div className="flex items-start gap-2">
                      <FileImage className="size-4 mt-0.5 text-gray-500 flex-shrink-0" />
                      <div>
                        <p className="text-gray-500">Artwork</p>
                        <p className="font-medium">{result.artworkName}</p>
                      </div>
                    </div>

                    <div className="flex items-start gap-2">
                      <Calendar className="size-4 mt-0.5 text-gray-500 flex-shrink-0" />
                      <div>
                        <p className="text-gray-500">Analyzed</p>
                        <p className="font-medium">
                          {new Date(result.timestamp).toLocaleString()}
                        </p>
                      </div>
                    </div>

                    <Separator />

                    <div className="space-y-2">
                      <p className="text-gray-500">File Information</p>
                      <p className="text-xs break-all">{result.fileName}</p>
                      <p className="text-xs text-gray-500">
                        {(result.fileSize / 1024 / 1024).toFixed(2)} MB
                      </p>
                    </div>
                  </div>
                </CardContent>
              </Card>
            </div>

            {/* Right Column - Score and Analysis */}
            <div className="lg:col-span-2 space-y-6">
              {/* Score Section */}
              <Card>
                <CardHeader>
                  <CardTitle>{primaryScoreTitle(result)}</CardTitle>
                  <CardDescription>{primaryScoreDescription(result)}</CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  {predLabel && (
                    <p className="text-center text-sm text-muted-foreground">
                      Model prediction:{" "}
                      <span className="font-semibold text-foreground">{predLabel}</span>
                    </p>
                  )}
                  {/* Large Score Display */}
                  <div className="text-center py-6">
                    {isInferenceFailed(result) ? (
                      <>
                        <div className="text-2xl mb-4 text-muted-foreground font-medium">
                          No authenticity score
                        </div>
                        <div className="relative h-4 bg-gray-200 rounded-full overflow-hidden">
                          <div className="absolute left-0 top-0 h-full w-0 bg-gray-400" />
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="text-6xl mb-4 tabular-nums">
                          {scorePercentage}
                          <span className="text-3xl text-gray-500">%</span>
                        </div>
                        <div className="relative h-4 bg-gray-200 rounded-full overflow-hidden">
                          <div
                            className={`absolute left-0 top-0 h-full ${getAnalysisBarColor(
                              result
                            )} transition-all`}
                            style={{ width: `${result.score * 100}%` }}
                          />
                        </div>
                      </>
                    )}
                  </div>

                  {/* Verdict */}
                  <Alert className={`${verdict.borderColor} ${verdict.bgColor}`}>
                    <VerdictIcon className={`size-5 ${verdict.color}`} />
                    <AlertDescription>
                      <span className={`font-semibold ${verdict.color}`}>
                        {verdict.text}
                      </span>
                    </AlertDescription>
                  </Alert>
                </CardContent>
              </Card>

              {/* Explanation Section */}
              <Card>
                <CardHeader>
                  <CardTitle>
                    {isInferenceFailed(result) ? "Details" : "Analysis Explanation"}
                  </CardTitle>
                  <CardDescription>
                    {isInferenceFailed(result)
                      ? "Why no score was produced for this upload"
                      : "Detailed AI-generated interpretation of the results"}
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {isLoadingExplanation ? (
                    <div className="flex items-center justify-center py-8 text-gray-500">
                      <Loader2 className="size-5 mr-2 animate-spin" />
                      Generating explanation...
                    </div>
                  ) : (
                    <p className="text-gray-700 leading-relaxed">{explanation}</p>
                  )}
                </CardContent>
              </Card>

              {/* Legend Section */}
              <Card>
                <CardHeader>
                  <CardTitle>Score interpretation</CardTitle>
                  <CardDescription>
                    {isInferenceFailed(result)
                      ? "Score ranges below do not apply when inference did not complete."
                      : usesAuthenticitySemantics(result)
                        ? "Authenticity confidence is the mean patch probability from the model (same signal as /inference)."
                        : "Older analyses used a forgery-oriented scale."}
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-3">
                    {isInferenceFailed(result) ? (
                      <Alert>
                        <AlertTriangle className="size-4" />
                        <AlertDescription>
                          This analysis did not finish successfully, so any placeholder values in
                          storage should be ignored. Try uploading again after the model service is
                          available.
                        </AlertDescription>
                      </Alert>
                    ) : usesAuthenticitySemantics(result) ? (
                      <>
                        <div className="flex gap-3">
                          <div className="size-8 rounded bg-green-100 flex items-center justify-center flex-shrink-0">
                            <CheckCircle className="size-5 text-green-600" />
                          </div>
                          <div>
                            <p className="font-medium text-green-700">
                              ~70–100% or prediction: Authentic
                            </p>
                            <p className="text-sm text-gray-600">
                              Stronger cues consistent with authentic work
                            </p>
                          </div>
                        </div>
                        <div className="flex gap-3">
                          <div className="size-8 rounded bg-yellow-100 flex items-center justify-center flex-shrink-0">
                            <AlertTriangle className="size-5 text-yellow-600" />
                          </div>
                          <div>
                            <p className="font-medium text-yellow-700">
                              Middle range — uncertain
                            </p>
                            <p className="text-sm text-gray-600">
                              Mixed patch signals; expert review recommended
                            </p>
                          </div>
                        </div>
                        <div className="flex gap-3">
                          <div className="size-8 rounded bg-red-100 flex items-center justify-center flex-shrink-0">
                            <AlertCircle className="size-5 text-red-600" />
                          </div>
                          <div>
                            <p className="font-medium text-red-700">
                              ~0–30% or prediction: Forgery
                            </p>
                            <p className="text-sm text-gray-600">
                              Cues more consistent with forgery or reproduction
                            </p>
                          </div>
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="flex gap-3">
                          <div className="size-8 rounded bg-green-100 flex items-center justify-center flex-shrink-0">
                            <CheckCircle className="size-5 text-green-600" />
                          </div>
                          <div>
                            <p className="font-medium text-green-700">
                              0.0 - 0.3: Likely Authentic
                            </p>
                            <p className="text-sm text-gray-600">
                              Lower score on legacy scale
                            </p>
                          </div>
                        </div>
                        <div className="flex gap-3">
                          <div className="size-8 rounded bg-yellow-100 flex items-center justify-center flex-shrink-0">
                            <AlertTriangle className="size-5 text-yellow-600" />
                          </div>
                          <div>
                            <p className="font-medium text-yellow-700">
                              0.3 - 0.7: Uncertain
                            </p>
                            <p className="text-sm text-gray-600">
                              Inconclusive on legacy scale
                            </p>
                          </div>
                        </div>
                        <div className="flex gap-3">
                          <div className="size-8 rounded bg-red-100 flex items-center justify-center flex-shrink-0">
                            <AlertCircle className="size-5 text-red-600" />
                          </div>
                          <div>
                            <p className="font-medium text-red-700">
                              0.7 - 1.0: Likely Forged
                            </p>
                            <p className="text-sm text-gray-600">
                              Higher score suggested forgery risk (legacy)
                            </p>
                          </div>
                        </div>
                      </>
                    )}
                  </div>

                  <Alert>
                    <AlertTriangle className="size-4" />
                    <AlertDescription>
                      <strong>Important:</strong> Scores are estimates based on AI
                      analysis. Always consult certified art experts and conduct
                      professional forensic testing for definitive authentication.
                    </AlertDescription>
                  </Alert>
                </CardContent>
              </Card>

              {/* Action Buttons */}
              <div className="flex gap-4">
                <Button asChild size="lg" className="flex-1">
                  <Link to="/upload">
                    <Upload className="size-4 mr-2" />
                    Analyze Another Artwork
                  </Link>
                </Button>
              </div>

              {/* Share and Download */}
              <div className="flex gap-4">
                <Button variant="outline" onClick={handleShare} className="flex-1">
                  <Share2 className="size-4 mr-2" />
                  Share Results
                </Button>
                <Button variant="outline" onClick={handleDownloadReport} className="flex-1">
                  <Download className="size-4 mr-2" />
                  Download Report
                </Button>
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}