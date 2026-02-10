/** Search request parameters sent by the backend in debug_mode SSE events for the debug panel. */
export type DebugSearchParams = {
  query: string;
  zipCode: string;
  radius: number;
  maxListings: number;
  threshold: number;
  extractDescriptions: boolean;
};
