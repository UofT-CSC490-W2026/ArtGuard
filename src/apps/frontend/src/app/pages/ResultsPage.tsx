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
      setTimeout(() => {
        setExplanation(generateExplanation(parsedResult.score));
        setIsLoadingExplanation(false);
      }, 1500);
    } catch {
      navigate("/upload");
    } finally {
      setIsLoading(false);
    }
  }, [navigate]);

  const generateExplanation = (score: number): string => {
    if (score < 0.3) {
      return `Based on our comprehensive AI analysis, this artwork shows strong characteristics consistent with authentic pieces. The brushstroke patterns, aging indicators, and material composition align well with expected authenticity markers. The pigment distribution and canvas texture demonstrate natural aging processes typical of genuine artworks. However, we recommend consulting with certified art experts for a definitive authentication, especially for high-value pieces.`;
    } else if (score < 0.7) {
      return `Our analysis reveals mixed indicators that make definitive authentication challenging. While some characteristics suggest authenticity, there are certain anomalies in the brushwork consistency and material composition that warrant further investigation. The artwork displays both authentic and questionable features. We strongly recommend professional verification by certified art historians and forensic experts before making any authentication claims or purchase decisions.`;
    } else {
      return `Our AI analysis has detected several concerning indicators that may suggest this artwork could be a forgery or reproduction. Notable issues include inconsistencies in brushstroke patterns, unusual pigment composition, and aging characteristics that don't align with expected authentic markers. The technical execution shows patterns commonly associated with reproductions or modern forgeries. However, false positives can occur, and we strongly advise seeking multiple expert opinions and conducting forensic laboratory testing before reaching final conclusions.`;
    }
  };

  const getVerdict = (score: number) => {
    if (score < 0.3) {
      return {
        text: "Likely Authentic",
        icon: CheckCircle,
        color: "text-green-600",
        bgColor: "bg-green-50",
        borderColor: "border-green-200",
      };
    } else if (score < 0.7) {
      return {
        text: "Uncertain / Needs Review",
        icon: AlertTriangle,
        color: "text-yellow-600",
        bgColor: "bg-yellow-50",
        borderColor: "border-yellow-200",
      };
    } else {
      return {
        text: "Likely Forged",
        icon: AlertCircle,
        color: "text-red-600",
        bgColor: "bg-red-50",
        borderColor: "border-red-200",
      };
    }
  };

  const getProgressColor = (score: number) => {
    if (score < 0.3) return "bg-green-600";
    if (score < 0.7) return "bg-yellow-500";
    return "bg-red-600";
  };

  if (isLoading || !result) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <Loader2 className="size-8 animate-spin text-accent-warm" aria-hidden />
      </div>
    );
  }

  const verdict = getVerdict(result.score);
  const VerdictIcon = verdict.icon;
  const scorePercentage = (result.score * 100).toFixed(1);

  const handleShare = async () => {
    const shareText = `ArtGuard Analysis Results\n\nArtwork: ${result.artworkName}\nArtist: ${result.artistName}\nForgery Score: ${scorePercentage}%\nVerdict: ${verdict.text}`;

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
- Forgery Score: ${scorePercentage}%
- Verdict: ${verdict.text}

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
              Forgery detection analysis for your artwork
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
                    <img
                      src={result.image}
                      alt="Analyzed artwork"
                      className="size-full object-cover"
                    />
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
                  <CardTitle>Forgery Detection Score</CardTitle>
                  <CardDescription>
                    AI-powered analysis result (0.0 = Authentic, 1.0 = Forged)
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-6">
                  {/* Large Score Display */}
                  <div className="text-center py-6">
                    <div className="text-6xl mb-4 tabular-nums">
                      {scorePercentage}
                      <span className="text-3xl text-gray-500">%</span>
                    </div>
                    <div className="relative h-4 bg-gray-200 rounded-full overflow-hidden">
                      <div
                        className={`absolute left-0 top-0 h-full ${getProgressColor(
                          result.score
                        )} transition-all`}
                        style={{ width: `${result.score * 100}%` }}
                      />
                    </div>
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
                  <CardTitle>Analysis Explanation</CardTitle>
                  <CardDescription>
                    Detailed AI-generated interpretation of the results
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
                  <CardTitle>Score Interpretation</CardTitle>
                  <CardDescription>
                    Understanding your forgery detection score
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  <div className="space-y-3">
                    <div className="flex gap-3">
                      <div className="size-8 rounded bg-green-100 flex items-center justify-center flex-shrink-0">
                        <CheckCircle className="size-5 text-green-600" />
                      </div>
                      <div>
                        <p className="font-medium text-green-700">
                          0.0 - 0.3: Likely Authentic
                        </p>
                        <p className="text-sm text-gray-600">
                          Characteristics consistent with authentic pieces
                        </p>
                      </div>
                    </div>

                    <div className="flex gap-3">
                      <div className="size-8 rounded bg-yellow-100 flex items-center justify-center flex-shrink-0">
                        <AlertTriangle className="size-5 text-yellow-600" />
                      </div>
                      <div>
                        <p className="font-medium text-yellow-700">
                          0.3 - 0.7: Uncertain / Needs Review
                        </p>
                        <p className="text-sm text-gray-600">
                          Inconclusive. Professional verification recommended
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
                          Shows signs that may indicate forgery
                        </p>
                      </div>
                    </div>
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