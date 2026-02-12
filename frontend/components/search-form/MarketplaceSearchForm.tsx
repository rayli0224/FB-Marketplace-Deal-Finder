"use client";

import { type UseFormRegister, type FieldErrors, type UseFormHandleSubmit, type UseFormWatch, type UseFormSetValue } from "react-hook-form";
import { type FormData as ValidationFormData, RADIUS_OPTIONS } from "@/lib/validation";
import { FormInputField } from "@/components/search-form/FormInputField";
import { CompactInlineToggle } from "@/components/ui/CompactInlineToggle";
import { InfoIcon } from "@/components/ui/InfoIcon";

const RADIUS_SELECT_BASE_CLASS =
  "w-full border-2 bg-secondary px-3 py-2.5 font-mono text-sm text-foreground focus:outline-none appearance-none pr-8 bg-no-repeat bg-[length:1rem] bg-[right_0.5rem_center] border-border focus:border-primary";
const RADIUS_SELECT_ERROR_CLASS = "border-destructive focus:border-destructive";
const RADIUS_SELECT_CHEVRON_URL =
  "url('data:image/svg+xml;charset=utf-8,%3Csvg%20xmlns%3D%22http%3A%2F%2Fwww.w3.org%2F2000%2Fsvg%22%20width%3D%2212%22%20height%3D%2212%22%20viewBox%3D%220%200%2012%2012%22%3E%3Cpath%20fill%3D%22currentColor%22%20d%3D%22M6%208L1%203h10z%22%2F%3E%3C%2Fsvg%3E')";

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
 * Fields: query, zip code, radius, threshold, max loot, and full-loot (description) toggle.
 * Submit button is disabled until all required fields are valid.
 */
export function MarketplaceSearchForm({ register, errors, isValid, handleSubmit, watch, setValue }: MarketplaceSearchFormProps) {
  return (
    <form onSubmit={handleSubmit} className="space-y-5">
      <div className="mb-4 font-mono text-xs text-muted-foreground">
        <span className="text-primary">{">"}</span> Enter target parameters, matey...
      </div>

      <FormInputField
        label="TARGET_QUERY"
        id="query"
        type="text"
        placeholder="e.g. iPhone 13 Pro"
        register={register}
        required
        error={errors.query?.message}
        tooltip="The search term for Facebook Marketplace—what you're looking for."
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
        placeholder="e.g. 10001"
        register={register}
        pattern="[0-9]{5}"
        required
        digitsOnly
        inputMode="numeric"
        error={errors.zipCode?.message}
        tooltip="5-digit ZIP code for your search area."
      />

      <div className="grid grid-cols-3 gap-4">
        <div>
          <label htmlFor="radius" className="mb-2 flex items-center gap-2 font-mono text-xs text-muted-foreground">
            <span className="text-primary">$</span>
            RAID_RADIUS
            <InfoIcon tooltip="Search radius in miles from your ZIP code." />
          </label>
          <div className="relative">
            <select
              id="radius"
              {...register("radius")}
              required
              className={`${RADIUS_SELECT_BASE_CLASS} [background-image:${RADIUS_SELECT_CHEVRON_URL}] ${errors.radius ? RADIUS_SELECT_ERROR_CLASS : ""}`}
            >
              {RADIUS_OPTIONS.map((miles) => (
                <option key={miles} value={miles}>
                  {miles} mi
                </option>
              ))}
            </select>
          </div>
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

