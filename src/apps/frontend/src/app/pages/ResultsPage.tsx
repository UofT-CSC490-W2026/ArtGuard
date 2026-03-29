import { useEffect, useState } from "react";
import { useNavigate, Link } from "react-router";
import { Header } from "../components/Header";
import { PatchOverlay } from "../components/PatchOverlay";
import { Button } from "../components/ui/button";
import { Loader2 } from "lucide-react";
import type { AnalysisResult } from "../types";
import {
  getAnalysisVerdict,
  isInferenceFailed,
  resolveDisplayedExplanation,
} from "../lib/analysisDisplay";

export function ResultsPage() {
  const navigate = useNavigate();
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [explanation, setExplanation] = useState("");
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem("artguard_latest_result");
    if (!stored) {
      navigate("/upload");
      return;
    }

    try {
      const parsed = JSON.parse(stored) as AnalysisResult;
      setResult(parsed);

      setExplanation(resolveDisplayedExplanation(parsed));
    } catch {
      navigate("/upload");
    } finally {
      setIsLoading(false);
    }
  }, [navigate]);

  if (isLoading || !result) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <Loader2 className="size-6 animate-spin" />
      </div>
    );
  }

  const failed = isInferenceFailed(result);
  const scorePercent = failed ? null : Math.round(result.score * 100);
  const verdict = getAnalysisVerdict(result);

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="mx-auto max-w-2xl px-6 py-16 text-center">
        {/* Image */}
        <div className="mb-10">
          {result.image && (
            <div className="relative inline-block">
              {result.patchData?.length ? (
                <PatchOverlay
                  imageSrc={result.image}
                  patchData={result.patchData}
                  imageWidth={result.imageWidth}
                  imageHeight={result.imageHeight}
                />
              ) : (
                <img
                  src={result.image}
                  alt=""
                  className="mx-auto max-h-[320px] object-contain rounded"
                />
              )}
            </div>
          )}
        </div>

        {/* Score: mean of per-patch authenticity probabilities */}
        <div className="mb-6">
          <div className="text-6xl font-serif tabular-nums text-foreground">
            {scorePercent !== null ? `${scorePercent}%` : "—"}
          </div>

          {/* Scientific progress bar */}
          <div className="mt-4 mx-auto w-full max-w-md">
            <div className="h-[2px] bg-border relative">
              <div
                className="absolute top-0 left-0 h-full bg-foreground/80 transition-all"
                style={{
                  width: scorePercent !== null ? `${scorePercent}%` : "0%",
                }}
              />
            </div>
          </div>

          <p className="mt-3 text-xs text-muted-foreground tracking-wide">
            PREDICTION CONFIDENCE
          </p>
          <p className="mt-2 text-xs text-muted-foreground/80 max-w-md mx-auto leading-relaxed">
            Mean of per-patch authenticity scores
          </p>
        </div>

        {/* Verdict */}
        <div className="mb-8">
          <p className={`text-lg font-medium ${verdict.color}`}>
            {verdict.text}
          </p>
        </div>

        {/* Explanation */}
        <div className="mb-12 max-w-xl mx-auto">
          <p className="text-sm text-muted-foreground leading-relaxed">
            {explanation}
          </p>
        </div>

        {/* Actions */}
        <div className="space-y-3">
          <Button asChild className="w-full">
            <Link to="/upload">Analyze another artwork</Link>
          </Button>

          <Button variant="outline" className="w-full" type="button" onClick={() => window.print()}>
            Download
          </Button>
        </div>
      </main>
    </div>
  );
}
