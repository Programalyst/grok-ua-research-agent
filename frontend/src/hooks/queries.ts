import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api } from "../api/client";
import type {
  GameCreate,
  GameProfileUpdate,
  GameUpdate,
  PostFilters,
  ResearchRunCreate,
  ScanCreate,
} from "../api/types";

export const queryKeys = {
  games: ["games"] as const,
  game: (gameId: string) => ["games", gameId] as const,
  profile: (gameId: string) => ["games", gameId, "profile"] as const,
  posts: (gameId: string, filters: PostFilters = {}) =>
    ["games", gameId, "posts", filters] as const,
  insights: (gameId: string) => ["games", gameId, "insights"] as const,
  scans: (gameId: string) => ["games", gameId, "scans"] as const,
  research: (gameId: string) => ["games", gameId, "research"] as const,
  researchEstimate: (gameId: string, caps: ResearchRunCreate) =>
    ["games", gameId, "research", "estimate", caps] as const,
  researchRun: (runId: string) => ["research", runId] as const,
};

export function useGames() {
  return useQuery({ queryKey: queryKeys.games, queryFn: api.listGames });
}

export function useGame(gameId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.game(gameId ?? ""),
    queryFn: () => api.getGame(gameId!),
    enabled: !!gameId,
  });
}

export function useCreateGame() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: GameCreate) => api.createGame(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.games }),
  });
}

export function useUpdateGame(gameId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: GameUpdate) => api.updateGame(gameId, body),
    onSuccess: (game) => {
      qc.setQueryData(queryKeys.game(gameId), game);
      return qc.invalidateQueries({ queryKey: queryKeys.games, exact: true });
    },
  });
}

export function useDeleteImage(gameId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (imageId: string) => api.deleteImage(gameId, imageId),
    onSettled: () =>
      qc.invalidateQueries({ queryKey: queryKeys.game(gameId), exact: true }),
  });
}

export function useProfile(gameId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.profile(gameId ?? ""),
    queryFn: async () => {
      try {
        return await api.getProfile(gameId!);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
    enabled: !!gameId,
  });
}

export function useGenerateProfile(gameId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.generateProfile(gameId),
    onSuccess: (profile) => qc.setQueryData(queryKeys.profile(gameId), profile),
  });
}

export function useSaveProfile(gameId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: GameProfileUpdate) => api.saveProfile(gameId, body),
    onSuccess: (profile) => qc.setQueryData(queryKeys.profile(gameId), profile),
  });
}

export function useRunScan(gameId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ScanCreate = {}) => api.runScan(gameId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["games", gameId] }),
  });
}

export function usePosts(
  gameId: string | undefined,
  filters: PostFilters = {},
) {
  return useQuery({
    queryKey: queryKeys.posts(gameId ?? "", filters),
    queryFn: () => api.listPosts(gameId!, filters),
    enabled: !!gameId,
  });
}

export function useInsights(gameId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.insights(gameId ?? ""),
    queryFn: () => api.getInsights(gameId!),
    enabled: !!gameId,
  });
}

export function useResearchEstimate(gameId: string, caps: ResearchRunCreate) {
  return useQuery({
    queryKey: queryKeys.researchEstimate(gameId, caps),
    queryFn: () => api.researchEstimate(gameId, caps),
  });
}

export function useResearchRuns(gameId: string) {
  return useQuery({
    queryKey: queryKeys.research(gameId),
    queryFn: () => api.listResearch(gameId),
  });
}

export function useResearchRun(runId: string | undefined) {
  return useQuery({
    queryKey: queryKeys.researchRun(runId ?? ""),
    queryFn: () => api.getResearch(runId!),
    enabled: !!runId,
  });
}

export function useRunResearch(gameId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (caps: ResearchRunCreate) => api.runResearch(gameId, caps),
    onSuccess: (run) => {
      qc.setQueryData(queryKeys.researchRun(run.id), run);
      return qc.invalidateQueries({ queryKey: queryKeys.research(gameId) });
    },
  });
}
