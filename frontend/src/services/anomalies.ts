import type { AnomalyQueue } from "../types/api";
import { apiFetch } from "./api";

export async function listAnomalies(limit = 200): Promise<AnomalyQueue> {
  return apiFetch<AnomalyQueue>(`/anomalies?limit=${limit}`);
}
