// Mirrors backend/app/schemas/dto.py
export type Language = "en" | "ja" | "ko" | "zh";
export type Sentiment = "positive" | "neutral" | "negative";
export type Category = "bug" | "praise" | "question" | "influencer" | "other";
export type ScanStatus = "pending" | "running" | "completed" | "failed";

export type Platform = "pc" | "console" | "ios" | "android" | "web" | "mac";
export type SuggestionStatus = "suggested" | "accepted" | "rejected";

export interface GameCreate {
  name: string;
  pitch?: string;
  description?: string;
  genres?: string[];
  platforms?: Platform[];
  regions?: string[];
  languages?: Language[];
  differentiators?: string;
  comparable_games?: string[];
  /** Per-language player phrasing, e.g. { zh: ['战棋', '末日'] } */
  seed_keywords?: Partial<Record<Language, string[]>>;
  keywords?: string[];
  hashtags?: string[];
  handles?: string[];
}

export type GameUpdate = Partial<GameCreate>;

export type ImageKind = "screenshot" | "key_art";

export interface GameImage {
  id: string;
  kind: ImageKind;
  width: number;
  height: number;
  filename: string;
  content_type: string;
  size_bytes: number;
  url: string;
  created_at: string;
}

export interface Game {
  id: string;
  name: string;
  pitch: string;
  description: string;
  genres: string[];
  platforms: Platform[];
  regions: string[];
  languages: Language[];
  differentiators: string;
  comparable_games: string[];
  seed_keywords: Partial<Record<Language, string[]>>;
  images: GameImage[];
  has_profile: boolean;
  keywords: string[];
  hashtags: string[];
  handles: string[];
  created_at: string;
}

export interface SuggestedComparable {
  name: string;
  reason: string;
  status: SuggestionStatus;
}

export interface GameProfileUpdate {
  themes: string[];
  keywords_by_language: Partial<Record<Language, string[]>>;
  suggested_comparables: SuggestedComparable[];
  visual_style: string[];
  target_audience: string;
}

export interface GameProfile extends GameProfileUpdate {
  game_id: string;
  generated_by: string;
  model: string;
  cost_usd: number | null;
  edited: boolean;
  updated_at: string;
}

export interface ScanCreate {
  max_posts?: number;
}

export interface Scan {
  id: string;
  game_id: string;
  provider: string;
  status: ScanStatus;
  post_count: number;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface Post {
  id: string;
  game_id: string;
  scan_id: string;
  text: string;
  author: string;
  author_followers: number;
  language: Language;
  sentiment: Sentiment;
  category: Category;
  url: string;
  posted_at: string;
  likes: number;
  reposts: number;
  replies: number;
  engagement: number;
}

export interface PostFilters {
  sentiment?: Sentiment;
  category?: Category;
  language?: Language;
  limit?: number;
}

export interface Insights {
  game_id: string;
  total_posts: number;
  sentiment_totals: Partial<Record<Sentiment, number>>;
  category_totals: Partial<Record<Category, number>>;
  language_totals: Partial<Record<Language, number>>;
  sentiment_over_time: {
    bucket_start: string;
    positive: number;
    neutral: number;
    negative: number;
  }[];
  top_issues: { label: string; count: number; example_post_ids: string[] }[];
  spikes: {
    post_id: string;
    author: string;
    engagement: number;
    reason: string;
  }[];
  generated_at: string;
}

export interface Health {
  status: string;
  provider: string;
}

// ---- research / UA brief ----

export interface ResearchRunCreate {
  max_posts_per_comparable?: number;
  max_posts_total?: number;
  max_searches?: number;
}

export interface ResearchEstimate {
  max_posts_per_comparable: number;
  max_posts_total: number;
  cost_per_post_usd: number;
  max_x_cost_usd: number;
  llm_reserve_usd: number;
  max_total_cost_usd: number;
  budget_limit_usd: number;
  budget_spent_today_usd: number;
  budget_remaining_usd: number;
  can_run: boolean;
  x_source: string;
  provider: string;
  comparables: string[];
  planned_queries: number;
  collector: string;
  max_searches: number;
  cost_per_search_usd: number;
  followers_verified: boolean;
}

export type FollowersSource = "x_api" | "grok_reported" | "unknown";

export interface PostRef {
  id: string;
  url: string;
  text: string;
  author: string;
  author_followers: number;
  author_followers_source: FollowersSource;
  language: string;
  comparable: string;
  engagement: number;
}

export interface UABrief {
  summary: string;
  model: string;
  player_phrasing: {
    phrase: string;
    language: string;
    meaning: string;
    example_post_ids: string[];
  }[];
  creative_hooks: {
    title: string;
    angle: string;
    differentiator: string;
    evidence_post_ids: string[];
  }[];
  competitor_insights: {
    comparable: string;
    complaints: string[];
    unmet_wants: string[];
    example_post_ids: string[];
  }[];
  creators: {
    handle: string;
    profile_url: string;
    followers: number;
    followers_source: FollowersSource;
    why: string;
    sample_post_id: string;
    sample_text: string;
  }[];
}

export interface ResearchRunSummary {
  id: string;
  game_id: string;
  status: "running" | "completed" | "failed";
  provider: string;
  x_source: string;
  max_posts_per_comparable: number;
  max_posts_total: number;
  post_count: number;
  author_count: number;
  x_cost_usd: number;
  llm_cost_usd: number;
  total_cost_usd: number;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export interface ResearchRun extends ResearchRunSummary {
  stats: Record<string, unknown>;
  brief: UABrief | null;
  posts: Record<string, PostRef>;
}
