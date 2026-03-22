import { useState } from "react";
import { Header } from "../components/Header";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Label } from "../components/ui/label";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "../components/ui/card";
import { Alert, AlertDescription } from "../components/ui/alert";
import { Textarea } from "../components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { getErrorMessage } from "../types";
import { api, hasApiBackend } from "../api/client";
import {
  startProcessDataPipeline,
  ragQuery,
  startTraining,
  startEvaluation,
} from "../api/backendApi";
import { Loader2 } from "lucide-react";

export function DeveloperPage() {
  const [ragQueryText, setRagQueryText] = useState("What is art authentication?");
  const [trainVariant, setTrainVariant] = useState<"tiny" | "base">("tiny");
  const [trainConfigJson, setTrainConfigJson] = useState("");
  const [evalVariant, setEvalVariant] = useState<"tiny" | "base">("tiny");
  const [evalCheckpoint, setEvalCheckpoint] = useState("/checkpoints/tiny/best.pt");

  const [loading, setLoading] = useState<string | null>(null);
  const [error, setError] = useState("");
  const [output, setOutput] = useState<string>("");

  const run = async (key: string, fn: () => Promise<unknown>) => {
    setError("");
    setOutput("");
    setLoading(key);
    try {
      const res = await fn();
      setOutput(JSON.stringify(res, null, 2));
    } catch (e) {
      setError(getErrorMessage(e));
    } finally {
      setLoading(null);
    }
  };

  if (!hasApiBackend()) {
    return (
      <div className="min-h-screen bg-background">
        <Header />
        <main className="container mx-auto px-4 py-8 max-w-2xl">
          <Alert>
            <AlertDescription>
              Set <code className="text-sm bg-muted px-1 rounded">VITE_API_URL</code> to your API
              base URL (e.g. ALB or CloudFront <code className="text-sm">/api</code> origin) and
              rebuild the frontend to use these tools.
            </AlertDescription>
          </Alert>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="container mx-auto px-4 py-8 max-w-3xl space-y-6">
        <div>
          <h1 className="text-3xl mb-2">Developer tools</h1>
          <p className="text-muted-foreground text-sm">
            Call backend operations used for data pipeline, RAG, and training. Requires appropriate
            AWS / Modal configuration on the server.
          </p>
        </div>

        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <Card>
          <CardHeader>
            <CardTitle>GET /health</CardTitle>
            <CardDescription>Quick connectivity check.</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              type="button"
              variant="outline"
              disabled={loading !== null}
              onClick={() => run("health", () => api.get<{ status: string }>("/health"))}
            >
              {loading === "health" && <Loader2 className="size-4 mr-2 animate-spin" />}
              Ping health
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>POST /process_data</CardTitle>
            <CardDescription>Spawn ECS data pipeline task (server-side config required).</CardDescription>
          </CardHeader>
          <CardContent>
            <Button
              type="button"
              disabled={loading !== null}
              onClick={() =>
                run("process", () => startProcessDataPipeline())
              }
            >
              {loading === "process" && <Loader2 className="size-4 mr-2 animate-spin" />}
              Run pipeline
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>POST /rag-query</CardTitle>
            <CardDescription>Bedrock Knowledge Base retrieval + generation.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              <Label htmlFor="rag-q">Query</Label>
              <Textarea
                id="rag-q"
                value={ragQueryText}
                onChange={(e) => setRagQueryText(e.target.value)}
                rows={3}
              />
            </div>
            <Button
              type="button"
              disabled={loading !== null || !ragQueryText.trim()}
              onClick={() => run("rag", () => ragQuery(ragQueryText.trim()))}
            >
              {loading === "rag" && <Loader2 className="size-4 mr-2 animate-spin" />}
              Query
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>POST /train</CardTitle>
            <CardDescription>Start Modal training run (tiny or base).</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              <Label>Variant</Label>
              <Select
                value={trainVariant}
                onValueChange={(v) => setTrainVariant(v as "tiny" | "base")}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="tiny">tiny</SelectItem>
                  <SelectItem value="base">base</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="train-cfg">Optional config overrides (JSON object)</Label>
              <Textarea
                id="train-cfg"
                placeholder='{"learning_rate": 0.0001}'
                value={trainConfigJson}
                onChange={(e) => setTrainConfigJson(e.target.value)}
                rows={4}
                className="font-mono text-sm"
              />
            </div>
            <Button
              type="button"
              disabled={loading !== null}
              onClick={() =>
                run("train", () => {
                  let config: Record<string, unknown> | undefined;
                  const t = trainConfigJson.trim();
                  if (t) {
                    config = JSON.parse(t) as Record<string, unknown>;
                    if (typeof config !== "object" || config === null || Array.isArray(config)) {
                      throw new Error("Config must be a JSON object");
                    }
                  }
                  return startTraining({ variant: trainVariant, config });
                })
              }
            >
              {loading === "train" && <Loader2 className="size-4 mr-2 animate-spin" />}
              Start training
            </Button>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>POST /evaluate</CardTitle>
            <CardDescription>Start Modal evaluation for a checkpoint path.</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="space-y-2">
              <Label>Variant</Label>
              <Select
                value={evalVariant}
                onValueChange={(v) => setEvalVariant(v as "tiny" | "base")}
              >
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="tiny">tiny</SelectItem>
                  <SelectItem value="base">base</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="eval-ckpt">Checkpoint path</Label>
              <Input
                id="eval-ckpt"
                value={evalCheckpoint}
                onChange={(e) => setEvalCheckpoint(e.target.value)}
                className="font-mono text-sm"
              />
            </div>
            <Button
              type="button"
              disabled={loading !== null || !evalCheckpoint.trim()}
              onClick={() =>
                run("eval", () =>
                  startEvaluation({
                    variant: evalVariant,
                    checkpoint: evalCheckpoint.trim(),
                  })
                )
              }
            >
              {loading === "eval" && <Loader2 className="size-4 mr-2 animate-spin" />}
              Start evaluation
            </Button>
          </CardContent>
        </Card>

        {output && (
          <Card>
            <CardHeader>
              <CardTitle>Last response</CardTitle>
            </CardHeader>
            <CardContent>
              <pre className="text-xs bg-muted p-4 rounded-lg overflow-auto max-h-96 whitespace-pre-wrap break-all">
                {output}
              </pre>
            </CardContent>
          </Card>
        )}
      </main>
    </div>
  );
}
