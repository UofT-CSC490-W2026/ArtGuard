import { useState, useEffect } from "react";
import { useNavigate, Link } from "react-router";
import { useAuth } from "../contexts/AuthContext";
import { Header } from "../components/Header";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Badge } from "../components/ui/badge";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "../components/ui/alert-dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Search, Filter, Calendar, Trash2, Eye } from "lucide-react";
import type { AnalysisResult } from "../types";
import { hasApiBackend } from "../api/client";
import {
  formatAnalysisScorePercent,
  getBatchIndicator,
  isInferenceFailed,
  matchesAuthenticFilter,
  matchesFailedInferenceFilter,
  matchesForgedFilter,
  matchesUncertainFilter,
  usesAuthenticitySemantics,
} from "../lib/analysisDisplay";
import {
  deleteAllInferences,
  deleteInference,
  inferenceToAnalysisResult,
  listInferences,
} from "../api/inferencesApi";
import { getErrorMessage } from "../types";
import { Loader2 } from "lucide-react";

export function HistoryPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [history, setHistory] = useState<AnalysisResult[]>([]);
  const [filteredHistory, setFilteredHistory] = useState<AnalysisResult[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [scoreFilter, setScoreFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<string>("newest");
  const [loadError, setLoadError] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;

    if (!hasApiBackend()) {
      const storedHistory = localStorage.getItem(`artguard_history_${user.id}`);
      if (storedHistory) {
        try {
          const parsedHistory = JSON.parse(storedHistory) as AnalysisResult[];
          setHistory(parsedHistory);
        } catch {
          setHistory([]);
        }
      } else {
        setHistory([]);
      }
      setLoadError("");
      setNextCursor(null);
      return;
    }

    let cancelled = false;
    (async () => {
      setIsLoading(true);
      setLoadError("");
      setNextCursor(null);
      try {
        const res = await listInferences(50);
        if (cancelled) return;
        setHistory(res.items.map(inferenceToAnalysisResult));
        setNextCursor(res.next_cursor ?? null);
      } catch (e) {
        if (!cancelled) setLoadError(getErrorMessage(e));
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [user]);

  useEffect(() => {
    // Apply filters and search
    let filtered = [...history];

    // Search filter
    if (searchQuery.trim()) {
      filtered = filtered.filter(
        (item) =>
          item.artistName.toLowerCase().includes(searchQuery.toLowerCase()) ||
          item.artworkName.toLowerCase().includes(searchQuery.toLowerCase()) ||
          item.fileName.toLowerCase().includes(searchQuery.toLowerCase())
      );
    }

    // Score filter (per-item semantics: API = authenticity; old localStorage = legacy forgery scale)
    if (scoreFilter !== "all") {
      filtered = filtered.filter((item) => {
        if (scoreFilter === "failed") return matchesFailedInferenceFilter(item);
        if (isInferenceFailed(item)) return false;
        if (scoreFilter === "authentic") return matchesAuthenticFilter(item);
        if (scoreFilter === "uncertain") return matchesUncertainFilter(item);
        if (scoreFilter === "forged") return matchesForgedFilter(item);
        return true;
      });
    }

    // Sort
    filtered.sort((a, b) => {
      if (sortBy === "newest") {
        return new Date(b.timestamp).getTime() - new Date(a.timestamp).getTime();
      } else if (sortBy === "oldest") {
        return new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime();
      } else if (sortBy === "score-high") {
        return b.score - a.score;
      } else if (sortBy === "score-low") {
        return a.score - b.score;
      }
      return 0;
    });

    setFilteredHistory(filtered);
  }, [searchQuery, scoreFilter, sortBy, history]);

  const getHistoryBadge = (item: AnalysisResult) => {
    const { icon, color, label } = getBatchIndicator(item, item.score);
    const classNameByColor: Record<string, string> = {
      "text-green-600": "bg-green-100 text-green-700 hover:bg-green-100",
      "text-yellow-600": "bg-yellow-100 text-yellow-700 hover:bg-yellow-100",
      "text-red-600": "bg-red-100 text-red-700 hover:bg-red-100",
      "text-gray-700": "bg-gray-200 text-gray-800 hover:bg-gray-200",
    };
    return {
      label,
      className: classNameByColor[color] ?? "bg-gray-100 text-gray-700 hover:bg-gray-100",
      icon,
    };
  };

  const handleViewResult = (item: AnalysisResult) => {
    // Set this as the latest result and navigate to results page
    localStorage.setItem("artguard_latest_result", JSON.stringify(item));
    navigate("/results");
  };

  const handleDeleteItem = async (id: string) => {
    if (hasApiBackend()) {
      try {
        await deleteInference(id);
        setHistory((prev) => prev.filter((item) => item.id !== id));
      } catch (e) {
        setLoadError(getErrorMessage(e));
      }
      return;
    }
    const updated = history.filter((item) => item.id !== id);
    setHistory(updated);
    localStorage.setItem(`artguard_history_${user?.id}`, JSON.stringify(updated));
  };

  const clearAllHistory = async () => {
    if (hasApiBackend()) {
      try {
        await deleteAllInferences();
        setHistory([]);
        setFilteredHistory([]);
        setNextCursor(null);
      } catch (e) {
        setLoadError(getErrorMessage(e));
      }
      return;
    }
    setHistory([]);
    setFilteredHistory([]);
    localStorage.removeItem(`artguard_history_${user?.id}`);
  };

  const handleLoadMore = async () => {
    if (!nextCursor || !hasApiBackend()) return;
    setIsLoadingMore(true);
    setLoadError("");
    try {
      const res = await listInferences(50, nextCursor);
      setHistory((prev) => [...prev, ...res.items.map(inferenceToAnalysisResult)]);
      setNextCursor(res.next_cursor ?? null);
    } catch (e) {
      setLoadError(getErrorMessage(e));
    } finally {
      setIsLoadingMore(false);
    }
  };

  return (
    <div className="min-h-screen bg-background">
      <Header />

      <main className="container mx-auto px-4 py-8">
        <div className="max-w-6xl mx-auto">
          <div className="mb-8 flex items-center justify-between">
            <div>
              <h1 className="text-3xl mb-2">Analysis History</h1>
              <p className="text-gray-600">
                View and manage your past analyses (authenticity confidence from the API, or legacy score scale for older saves)
              </p>
            </div>
            {history.length > 0 && !isLoading && (
              <AlertDialog>
                <AlertDialogTrigger asChild>
                  <Button variant="outline">
                    <Trash2 className="size-4 mr-2" />
                    Clear All
                  </Button>
                </AlertDialogTrigger>
                <AlertDialogContent>
                  <AlertDialogHeader>
                    <AlertDialogTitle>Clear all history?</AlertDialogTitle>
                    <AlertDialogDescription>
                      This will permanently delete all your analysis history. This action cannot be undone.
                    </AlertDialogDescription>
                  </AlertDialogHeader>
                  <AlertDialogFooter>
                    <AlertDialogCancel>Cancel</AlertDialogCancel>
                    <AlertDialogAction onClick={() => void clearAllHistory()}>
                      Clear All
                    </AlertDialogAction>
                  </AlertDialogFooter>
                </AlertDialogContent>
              </AlertDialog>
            )}
          </div>

          {/* Filters */}
          <Card className="mb-6">
            <CardContent className="pt-6">
              <div className="grid md:grid-cols-3 gap-4">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 size-4 text-gray-400" />
                  <Input
                    placeholder="Search artist, artwork, or filename..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    className="pl-9"
                  />
                </div>

                <Select value={scoreFilter} onValueChange={setScoreFilter}>
                  <SelectTrigger>
                    <Filter className="size-4 mr-2" />
                    <SelectValue placeholder="Filter by score" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Results</SelectItem>
                    <SelectItem value="authentic">Likely authentic</SelectItem>
                    <SelectItem value="uncertain">Uncertain</SelectItem>
                    <SelectItem value="forged">Likely forgery / forged</SelectItem>
                    <SelectItem value="failed">Inference failed</SelectItem>
                  </SelectContent>
                </Select>

                <Select value={sortBy} onValueChange={setSortBy}>
                  <SelectTrigger>
                    <Calendar className="size-4 mr-2" />
                    <SelectValue placeholder="Sort by" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="newest">Newest First</SelectItem>
                    <SelectItem value="oldest">Oldest First</SelectItem>
                    <SelectItem value="score-high">Highest Score</SelectItem>
                    <SelectItem value="score-low">Lowest Score</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </CardContent>
          </Card>

          {loadError && (
            <div className="mb-4 rounded-lg border border-destructive/50 bg-destructive/10 px-4 py-3 text-sm text-destructive">
              {loadError}
            </div>
          )}

          {isLoading ? (
            <Card>
              <CardContent className="py-16 flex flex-col items-center justify-center gap-3 text-muted-foreground">
                <Loader2 className="size-10 animate-spin" />
                <p>Loading history…</p>
              </CardContent>
            </Card>
          ) : null}

          {/* History List */}
          {!isLoading && filteredHistory.length === 0 ? (
            <Card>
              <CardContent className="py-16 text-center">
                <div className="text-gray-400 mb-4">
                  <Calendar className="size-16 mx-auto" />
                </div>
                <h3 className="text-xl mb-2">
                  {history.length === 0 ? "No analysis history yet" : "No results found"}
                </h3>
                <p className="text-gray-500 mb-6">
                  {history.length === 0
                    ? "Upload an artwork to start analyzing"
                    : "Try adjusting your filters"}
                </p>
                {history.length === 0 && (
                  <Button asChild>
                    <Link to="/upload">Upload Artwork</Link>
                  </Button>
                )}
              </CardContent>
            </Card>
          ) : !isLoading ? (
            <div className="space-y-4">
              {filteredHistory.map((item) => {
                const badge = getHistoryBadge(item);
                const BadgeIcon = badge.icon;

                return (
                  <Card key={item.id} className="hover:shadow-md transition-shadow">
                    <CardContent className="p-4">
                      <div className="flex gap-4">
                        <div className="size-24 flex-shrink-0 rounded overflow-hidden bg-gray-100">
                          {item.image ? (
                            <img
                              src={item.image}
                              alt={item.artworkName}
                              className="size-full object-cover"
                            />
                          ) : (
                            <div className="size-full flex items-center justify-center text-xs text-muted-foreground p-1 text-center">
                              No preview
                            </div>
                          )}
                        </div>

                        <div className="flex-1 min-w-0">
                          <div className="flex items-start justify-between gap-4 mb-2">
                            <div className="flex-1 min-w-0">
                              <h3 className="font-semibold truncate">
                                {item.artworkName}
                              </h3>
                              <p className="text-sm text-gray-600 truncate">
                                by {item.artistName}
                              </p>
                            </div>
                            <Badge variant="secondary" className={badge.className}>
                              <BadgeIcon className="size-3 mr-1" />
                              {badge.label}
                            </Badge>
                          </div>

                          <div className="flex items-center gap-4 text-sm text-gray-500 mb-3">
                            <span>
                              {isInferenceFailed(item)
                                ? "No score — inference failed"
                                : usesAuthenticitySemantics(item)
                                  ? `Authenticity: ${formatAnalysisScorePercent(item)}%`
                                  : `Score: ${formatAnalysisScorePercent(item)}%`}
                            </span>
                            <span>•</span>
                            <span>
                              {new Date(item.timestamp).toLocaleDateString()} at{" "}
                              {new Date(item.timestamp).toLocaleTimeString()}
                            </span>
                            <span>•</span>
                            <span className="truncate">{item.fileName}</span>
                          </div>

                          <div className="flex gap-2">
                            <Button
                              size="sm"
                              onClick={() => handleViewResult(item)}
                            >
                              <Eye className="size-4 mr-2" />
                              View Details
                            </Button>
                            <Button
                              size="sm"
                              variant="outline"
                              onClick={() => void handleDeleteItem(item.id)}
                            >
                              <Trash2 className="size-4 mr-2" />
                              Delete
                            </Button>
                          </div>
                        </div>
                      </div>
                    </CardContent>
                  </Card>
                );
              })}
              {hasApiBackend() && nextCursor && (
                <div className="flex justify-center pt-4">
                  <Button
                    variant="outline"
                    disabled={isLoadingMore}
                    onClick={() => void handleLoadMore()}
                  >
                    {isLoadingMore ? (
                      <>
                        <Loader2 className="size-4 mr-2 animate-spin" />
                        Loading…
                      </>
                    ) : (
                      "Load more"
                    )}
                  </Button>
                </div>
              )}
            </div>
          ) : null}

          {!isLoading && filteredHistory.length > 0 && (
            <div className="mt-6 text-center text-sm text-gray-500">
              Showing {filteredHistory.length} of {history.length} results
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
