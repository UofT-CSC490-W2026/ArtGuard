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
import {
  AlertCircle,
  CheckCircle,
  AlertTriangle,
  Search,
  Filter,
  Calendar,
  Trash2,
  Eye,
} from "lucide-react";
import type { AnalysisResult } from "../types";

export function HistoryPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const [history, setHistory] = useState<AnalysisResult[]>([]);
  const [filteredHistory, setFilteredHistory] = useState<AnalysisResult[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [scoreFilter, setScoreFilter] = useState<string>("all");
  const [sortBy, setSortBy] = useState<string>("newest");

  useEffect(() => {
    // Load history from localStorage
    const storedHistory = localStorage.getItem(`artguard_history_${user?.id}`);
    if (storedHistory) {
      const parsedHistory = JSON.parse(storedHistory);
      setHistory(parsedHistory);
      setFilteredHistory(parsedHistory);
    }
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

    // Score filter
    if (scoreFilter !== "all") {
      filtered = filtered.filter((item) => {
        if (scoreFilter === "authentic") return item.score < 0.3;
        if (scoreFilter === "uncertain") return item.score >= 0.3 && item.score < 0.7;
        if (scoreFilter === "forged") return item.score >= 0.7;
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

  const getScoreBadge = (score: number) => {
    if (score < 0.3) {
      return {
        label: "Authentic",
        variant: "default" as const,
        className: "bg-green-100 text-green-700 hover:bg-green-100",
        icon: CheckCircle,
      };
    } else if (score < 0.7) {
      return {
        label: "Uncertain",
        variant: "secondary" as const,
        className: "bg-yellow-100 text-yellow-700 hover:bg-yellow-100",
        icon: AlertTriangle,
      };
    } else {
      return {
        label: "Forged",
        variant: "destructive" as const,
        className: "bg-red-100 text-red-700 hover:bg-red-100",
        icon: AlertCircle,
      };
    }
  };

  const handleViewResult = (item: AnalysisResult) => {
    // Set this as the latest result and navigate to results page
    localStorage.setItem("artguard_latest_result", JSON.stringify(item));
    navigate("/results");
  };

  const handleDeleteItem = (id: string) => {
    const updated = history.filter((item) => item.id !== id);
    setHistory(updated);
    localStorage.setItem(`artguard_history_${user?.id}`, JSON.stringify(updated));
  };

  const clearAllHistory = () => {
    setHistory([]);
    setFilteredHistory([]);
    localStorage.removeItem(`artguard_history_${user?.id}`);
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
                View and manage your past forgery detection analyses
              </p>
            </div>
            {history.length > 0 && (
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
                    <AlertDialogAction onClick={clearAllHistory}>
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
                    <SelectItem value="authentic">Authentic (0.0-0.3)</SelectItem>
                    <SelectItem value="uncertain">Uncertain (0.3-0.7)</SelectItem>
                    <SelectItem value="forged">Forged (0.7-1.0)</SelectItem>
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

          {/* History List */}
          {filteredHistory.length === 0 ? (
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
          ) : (
            <div className="space-y-4">
              {filteredHistory.map((item) => {
                const badge = getScoreBadge(item.score);
                const BadgeIcon = badge.icon;

                return (
                  <Card key={item.id} className="hover:shadow-md transition-shadow">
                    <CardContent className="p-4">
                      <div className="flex gap-4">
                        <div className="size-24 flex-shrink-0 rounded overflow-hidden bg-gray-100">
                          <img
                            src={item.image}
                            alt={item.artworkName}
                            className="size-full object-cover"
                          />
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
                            <Badge className={badge.className}>
                              <BadgeIcon className="size-3 mr-1" />
                              {badge.label}
                            </Badge>
                          </div>

                          <div className="flex items-center gap-4 text-sm text-gray-500 mb-3">
                            <span>Score: {(item.score * 100).toFixed(1)}%</span>
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
                              onClick={() => handleDeleteItem(item.id)}
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
            </div>
          )}

          {filteredHistory.length > 0 && (
            <div className="mt-6 text-center text-sm text-gray-500">
              Showing {filteredHistory.length} of {history.length} results
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
