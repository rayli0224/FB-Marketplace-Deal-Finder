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
 * Validates query (required), zipCode (digits only, exactly 5), radius (1-500 miles), and threshold (0-100%).
 * Uses Zod's preprocess to handle empty string inputs from number fields before converting to numbers.
 * Provides specific error messages for different failure types: missing input, non-numeric characters,
 * wrong length, and out-of-range values.
 */
export const formSchema = z.object({
  query: z.string().min(1, "Query is required"),
  zipCode: z
    .string()
    .min(1, "Zip code is required")
    .refine((val: string) => /^\d+$/.test(val), { message: "Zip code must contain only digits" })
    .refine((val: string) => val.length === 5, { message: "Zip code must be exactly 5 digits" }),
  radius: z.preprocess(
    preprocessNumber,
    z.number({ required_error: "Radius is required" })
      .min(1, "Radius must be between 1 and 500 miles")
      .max(500, "Radius must be between 1 and 500 miles")
  ),
  threshold: z.preprocess(
    preprocessNumber,
    z.number({ required_error: "Threshold is required" })
      .min(0, "Threshold must be between 0% and 100%")
      .max(100, "Threshold must be between 0% and 100%")
  ),
  extractDescriptions: z.boolean().default(false),
});

export type FormData = z.infer<typeof formSchema>;
