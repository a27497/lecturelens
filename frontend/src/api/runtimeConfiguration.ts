import { http } from "./http";

type ApiResponse<T> = { data: T };

export type PublicRuntimeConfiguration = {
  demoMode: boolean;
};

export async function fetchPublicRuntimeConfiguration(): Promise<PublicRuntimeConfiguration> {
  const response = await http.get<ApiResponse<PublicRuntimeConfiguration>>("/api/public/runtime-configuration");
  return response.data.data;
}
