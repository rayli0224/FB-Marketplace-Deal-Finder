import { z } from "zod";

/**
 * Converts empty string, undefined, or null to undefined, otherwise converts to number.
 * Used to preprocess form inputs that may be empty strings before validation.
 */
function preprocessNumber(val: unknown): number | undefined {
  if (val === "" || val === undefined || val === null) return undefined;
  return Number(val);
}

/**
 * Validation schema for the marketplace search form.
 * Validates query (required), zipCode (5 digits), radius (1-500 miles), and threshold (0-100%).
 * Uses Zod's preprocess to handle empty string inputs from number fields before converting to numbers.
 */
export const formSchema = z.object({
  query: z.string().min(1, "Query is required"),
  zipCode: z
    .string()
    .min(1, "Zip code is required")
    .regex(/^[0-9]{5}$/, "Zip code must be 5 digits"),
  radius: z.preprocess(
    preprocessNumber,
    z.number({ required_error: "Radius is required" })
      .min(1, "Radius must be at least 1 mile")
      .max(500, "Radius must be at most 500 miles")
  ),
  threshold: z.preprocess(
    preprocessNumber,
    z.number({ required_error: "Threshold is required" })
      .min(0, "Threshold must be at least 0%")
      .max(100, "Threshold must be at most 100%")
  ),
});

export type FormData = z.infer<typeof formSchema>;
