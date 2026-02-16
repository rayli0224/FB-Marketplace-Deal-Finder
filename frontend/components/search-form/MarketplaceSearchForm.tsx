"use client";

import { type UseFormRegister, type FieldErrors, type UseFormHandleSubmit, type UseFormWatch, type UseFormSetValue } from "react-hook-form";
import { type FormData as ValidationFormData, RADIUS_OPTIONS } from "@/lib/validation";
import { QueryInputWithSuggestions } from "@/components/search-form/QueryInputWithSuggestions";
import { FormInputField } from "@/components/search-form/FormInputField";
import { Combobox } from "@/components/ui/Combobox";
import { CompactInlineToggle } from "@/components/ui/CompactInlineToggle";
import { InfoIcon } from "@/components/ui/InfoIcon";

export interface MarketplaceSearchFormProps {
  register: UseFormRegister<ValidationFormData>;
  errors: FieldErrors<ValidationFormData>;
  isValid: boolean;
  handleSubmit: UseFormHandleSubmit<ValidationFormData>;
  watch: UseFormWatch<ValidationFormData>;
  setValue: UseFormSetValue<ValidationFormData>;
}

/**
 * Search form component for marketplace search parameters.
 * Fields: query, location (city or postal code), radius, threshold, max loot, and full-loot (description) toggle.
 * Submit button is disabled until all required fields are valid.
 */
export function MarketplaceSearchForm({ register, errors, isValid, handleSubmit, watch, setValue }: MarketplaceSearchFormProps) {
  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div className="mb-4 font-mono text-xs text-muted-foreground">
        <span className="text-primary">{">"}</span> Enter target parameters, matey...
      </div>

      <QueryInputWithSuggestions
        register={register}
        queryValue={watch("query")}
        error={errors.query?.message}
        afterLabel={
          <CompactInlineToggle
            id="extractDescriptions"
            label="FULL_LOOT"
            checked={watch("extractDescriptions")}
            onChange={(checked) => setValue("extractDescriptions", checked, { shouldValidate: true })}
            tooltip={'On: Ransack full listing text for each haul (better accuracy, slower).\nOff: Titles only (faster, less accurate for complex loot).'}
          />
        }
      />

      <FormInputField
        label="PORT_CODE"
        id="zipCode"
        type="text"
        placeholder="e.g. New York, NY or 10001"
        register={register}
        required
        error={errors.zipCode?.message}
        tooltip="City name or postal code for your search area. Zip codes work best in the US."
      />

      <div className="grid grid-cols-3 gap-4">
        <div>
          <label htmlFor="radius" className="mb-2 flex items-center gap-2 font-mono text-xs text-muted-foreground">
            <span className="text-primary">$</span>
            RAID_RADIUS
            <InfoIcon tooltip="Search radius in miles from your location." />
          </label>
          <Combobox
            id="radius"
            register={register("radius")}
            options={RADIUS_OPTIONS}
            getOptionValue={(option) => String(option)}
            getOptionLabel={(option) => `${option} mi`}
            placeholder="Select radius..."
            error={errors.radius?.message}
            required
          />
          {errors.radius?.message && (
            <p className="mt-1 font-mono text-xs text-destructive">{errors.radius.message}</p>
          )}
        </div>

        <FormInputField
          label="STEAL_THRESHOLD"
          id="threshold"
          type="text"
          placeholder="80"
          register={register}
          min={0}
          max={100}
          required
          digitsOnly
          inputMode="numeric"
          error={errors.threshold?.message}
          suffix="%"
          tooltip="Max % of eBay average price. Example: 80% shows only listings at 80% of market value or below."
        />

        <FormInputField
          label="MAX_LOOT"
          id="maxListings"
          type="text"
          placeholder="10"
          register={register}
          min={1}
          max={200}
          required
          digitsOnly
          inputMode="numeric"
          error={errors.maxListings?.message}
          tooltip="Maximum number of listings to scan; fewer is faster."
        />
      </div>

      <button
        type="submit"
        disabled={!isValid}
        className={`group mt-2 w-full border-2 px-4 py-3 font-mono text-sm font-bold uppercase tracking-wide transition-all ${
          isValid
            ? "border-primary bg-primary text-primary-foreground hover:bg-transparent hover:text-primary cursor-pointer"
            : "border-muted bg-muted text-muted-foreground cursor-not-allowed opacity-50"
        }`}
      >
        <span className={`inline-block transition-transform ${isValid ? "group-hover:translate-x-1" : ""}`}>
          {">>>"} BEGIN HEIST {"<<<"}
        </span>
      </button>
    </form>
  );
}

