import type {
  Game,
  GameCreate,
  GameProfile,
  GameProfileUpdate,
  GameUpdate,
  Health,
  GameImage,
  ImageKind,
  Insights,
  Post,
  PostFilters,
  Scan,
  ScanCreate,
  ResearchEstimate,
  ResearchRun,
  ResearchRunCreate,
  ResearchRunSummary,
} from "./types";

const BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers:
      init?.body instanceof FormData
        ? init?.headers
        : { "Content-Type": "application/json", ...init?.headers },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = Array.isArray(body.detail)
      ? body.detail
          .map(
            (d: { loc?: unknown[]; msg?: string }) =>
              `${d.loc?.slice(1).join(".")}: ${d.msg}`,
          )
          .join("; ")
      : body.detail;
    throw new ApiError(
      res.status,
      typeof detail === "string" && detail ? detail : res.statusText,
    );
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

function qs(params: object): string {
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== "",
  );
  return entries.length
    ? `?${new URLSearchParams(entries.map(([k, v]) => [k, String(v)]))}`
    : "";
}

export const api = {
  health: () => request<Health>("/health"),
  listGames: () => request<Game[]>("/games"),
  createGame: (body: GameCreate) =>
    request<Game>("/games", { method: "POST", body: JSON.stringify(body) }),
  getGame: (id: string) => request<Game>(`/games/${id}`),
  updateGame: (id: string, body: GameUpdate) =>
    request<Game>(`/games/${id}`, {
      method: "PATCH",
      body: JSON.stringify(body),
    }),
  uploadImage: (gameId: string, file: File, kind: ImageKind) => {
    const form = new FormData();
    form.append("file", file);
    form.append("kind", kind);
    return request<GameImage>(`/games/${gameId}/images`, {
      method: "POST",
      body: form,
    });
  },
  deleteImage: (gameId: string, imageId: string) =>
    request<void>(`/games/${gameId}/images/${imageId}`, { method: "DELETE" }),
  generateProfile: (gameId: string) =>
    request<GameProfile>(`/games/${gameId}/profile/generate`, {
      method: "POST",
    }),
  getProfile: (gameId: string) =>
    request<GameProfile>(`/games/${gameId}/profile`),
  saveProfile: (gameId: string, body: GameProfileUpdate) =>
    request<GameProfile>(`/games/${gameId}/profile`, {
      method: "PUT",
      body: JSON.stringify(body),
    }),
  deleteGame: (id: string) =>
    request<void>(`/games/${id}`, { method: "DELETE" }),
  runScan: (gameId: string, body: ScanCreate = {}) =>
    request<Scan>(`/games/${gameId}/scans`, {
      method: "POST",
      body: JSON.stringify(body),
    }),
  listScans: (gameId: string) => request<Scan[]>(`/games/${gameId}/scans`),
  listPosts: (gameId: string, filters: PostFilters = {}) =>
    request<Post[]>(`/games/${gameId}/posts${qs(filters)}`),
  getInsights: (gameId: string) =>
    request<Insights>(`/games/${gameId}/insights`),
  researchEstimate: (gameId: string, caps: ResearchRunCreate = {}) =>
    request<ResearchEstimate>(`/games/${gameId}/research/estimate${qs(caps)}`),
  runResearch: (gameId: string, caps: ResearchRunCreate = {}) =>
    request<ResearchRun>(`/games/${gameId}/research`, {
      method: "POST",
      body: JSON.stringify(caps),
    }),
  listResearch: (gameId: string) =>
    request<ResearchRunSummary[]>(`/games/${gameId}/research`),
  getResearch: (runId: string) => request<ResearchRun>(`/research/${runId}`),
};
