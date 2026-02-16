import { z } from "zod";

/**
 * Converts empty string, undefined, or null to undefined, otherwise converts to number.
 * Used to preprocess form inputs that may be empty strings before validation.
 */
function preprocessNumber(val: unknown): number | undefined {
  if (val === "" || val === undefined || val === null) return undefined;
  return Number(val);
}

/** Supported radius values in miles (Facebook Marketplace location dialog). */
export const RADIUS_OPTIONS = [1, 2, 5, 10, 20, 40, 60, 80, 100, 250, 500] as const;

/** Default radius when the form has not been changed. Must be in RADIUS_OPTIONS. */
export const DEFAULT_RADIUS = 20;

/**
 * Validation schema for the marketplace search form.
 * Validates query (required), zipCode (required), radius (one of RADIUS_OPTIONS),
 * threshold (0-100%), and maxListings (1-200). Uses Zod's preprocess to handle empty
 * string inputs from number fields before converting to numbers. Provides specific
 * error messages for missing input, non-numeric characters, wrong length, and out-of-range values.
 */
export const formSchema = z.object({
  query: z.string().min(1, "Query is required"),
  zipCode: z.string().min(1, "Zip code is required"),
  radius: z.preprocess(
    preprocessNumber,
    z.number({ required_error: "Radius is required" }).refine(
      (n: number) => (RADIUS_OPTIONS as readonly number[]).includes(n),
      { message: "Radius must be one of the supported values" }
    )
  ),
  threshold: z.preprocess(
    preprocessNumber,
    z.number({ required_error: "Threshold is required" })
      .min(0, "Threshold must be between 0% and 100%")
      .max(100, "Threshold must be between 0% and 100%")
  ),
  maxListings: z.preprocess(
    preprocessNumber,
    z.number({ required_error: "Max listings is required" })
      .min(1, "Max listings must be between 1 and 200")
      .max(200, "Max listings must be between 1 and 200")
  ),
  extractDescriptions: z.boolean().default(false),
});

export type FormData = z.infer<typeof formSchema>;
